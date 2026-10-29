"""Public filing starting points and evidence tasks; no paid feed or inferred facts."""

from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from sec_filings import filing_check_lines


def safe_website(value):
    try:
        parsed = urlsplit(str(value or ""))
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
            return None
        return parsed.geturl()
    except ValueError:
        return None


def filing_review_plan(ticker, company=None, website=None):
    """Routes reflect the listing market, not a verified reporting jurisdiction."""
    links = []
    issuer = safe_website(website)
    if issuer:
        links.append({"label": "Issuer website — find investor relations and annual/interim reports",
                      "url": issuer, "role": "quote-provider website; verify issuer identity"})
    if ticker.endswith(".L"):
        links += [
            {"label": "FCA National Storage Mechanism", "url": "https://data.fca.org.uk/#/nsm/nationalstoragemechanism", "role": "UK regulated announcements and annual reports"},
            {"label": "Companies House", "url": "https://find-and-update.company-information.service.gov.uk/", "role": "UK registered-company accounts; confirm the listed parent"},
        ]
    elif ticker.endswith(".TA"):
        links.append({"label": "TASE MAYA financial statements", "url": "https://maya.tase.co.il/en/reports/financial-report", "role": "Israeli listing disclosures; confirm issuer and language"})
    elif ticker.endswith(".WA"):
        links.append({"label": "KNF issuer-information sources", "url": "https://www.knf.gov.pl/dla_konsumenta/kampanie_informacyjne/zrodla_informacji_o_emitentach", "role": "Official directory of Polish issuer/ESPI/EBI sources"})
    elif ticker.endswith(".DE"):
        links.append({"label": "German Company Register", "url": "https://www.unternehmensregister.de/en", "role": "Published company disclosures; some deposited documents can carry a fee"})
    else:
        links.append({"label": "SEC EDGAR filing search", "url": "https://www.sec.gov/search-filings", "role": "US filings where applicable; search issuer/ticker and confirm CIK"})
    tasks = [
        {"id": "identity", "question": "Confirm the listed issuer, reporting jurisdiction and latest annual/interim filing, including amendments."},
        {"id": "maturities", "question": "Find contractual debt/lease maturities through the next 24 months; record actual dates, amounts, currency and units."},
        {"id": "covenants", "question": "Check covenant thresholds/headroom, breaches, waivers and clauses that can accelerate repayment."},
        {"id": "liquidity", "question": "Identify unrestricted cash, restricted cash and committed undrawn facilities; record expiry dates and draw conditions."},
        {"id": "going_concern", "question": "Read the auditor opinion and going-concern/liquidity disclosures, and subsequent events."},
        {"id": "interest", "question": "Reconcile gross interest, lease liabilities and cash-flow classification if the provider's interest evidence is missing."},
        {"id": "catalyst", "question": "Source the negative event and recovery thesis; identify a measurable resolution condition and what would invalidate it."},
    ]
    return {"status": "PENDING_DOCUMENT_REVIEW", "search_term": company or ticker,
            "source_links": links, "checklist": tasks,
            "evidence_required": ["Filing URL", "Publication date", "Statement period", "Note/page", "Currency and units", "Finding and unresolved questions"],
            "notice": "Starting points only: a link or checklist does not verify the issuer, latest filing or any financial fact. No screening status is upgraded."}


def filing_links_html(plan):
    if not plan:
        return ""
    links = []
    for source in plan["source_links"]:
        url = safe_website(source["url"])
        if url:
            links.append(f'<li><a href="{escape(url, quote=True)}">{escape(source["label"])}</a></li>')
    return ("<div><h4>Public filing review</h4><p>Search for: " + escape(plan["search_term"])
            + "</p><ul>" + "".join(links) + "</ul><p>Verify debt maturities, covenants, unrestricted liquidity and going-concern disclosures. Review remains pending.</p></div>")


def write_filing_queue(audit, path):
    decisions = {"selected", "unverified", "specialist_review", "valuation_unverified", "currency_unverified", "event_review", "filing_review", "filing_unverified"}
    queued = [item for item in audit if item.get("decision") in decisions]
    lines = ["# Public filing review queue", "",
             "No paid data subscription is required for this workflow. Start with issuer investor-relations reports and the public filing sources below; source access can vary.", "",
             "Financial contents remain unverified until findings are actually checked. Official publication metadata, where available, is reported separately below.", ""]
    if not queued:
        lines += ["No candidates currently require this queue. An empty shortlist is valid; do not relax exclusions to force picks.", ""]
    for item in queued:
        plan = item.get("filing_review") or filing_review_plan(item["ticker"], item.get("company"))
        lines += [f"## {escape(item['ticker'])}", "", f"Search issuer name: {escape(plan['search_term'])}", "",
                  f"Scanner decision: {escape(item.get('decision', ''))}.", ""]
        if item.get("reason"):
            lines += [f"Decision reason: {escape(item['reason'])}", ""]
        solvency = item.get("solvency") or {}
        lines += filing_check_lines(item.get("official_filing_check"))
        hold = item.get("review_hold")
        if hold:
            lines += [f"Sourced hold (reviewed {escape(hold['reviewed_at'])}): {escape(hold['reason'])}", "",
                      f"Release condition: {escape(hold['release_condition'])}", "", "Finding sources:", ""]
            for source in hold["sources"]:
                url = safe_website(source["url"])
                if url:
                    lines.append(f"- [{escape(source['published_at'])} disclosure](<{url}>)")
            if hold.get("review_notes"):
                lines += ["", "Reviewed findings (the hold remains unresolved):", ""]
                for note in hold["review_notes"]:
                    lines.append(f"- {escape(note['finding'])} [{escape(note['published_at'])} source](<{note['source_url']}>)")
            lines += [""]
        questions = solvency.get("missing", []) + solvency.get("review", [])
        if questions:
            lines += ["Scanner questions:", ""] + [f"- {escape(question)}" for question in questions] + [""]
        lines += ["Public starting points:", ""]
        for source in plan["source_links"]:
            url = safe_website(source["url"])
            if url:
                # Angle-bracket destinations keep spaces/parentheses harmless.
                url = url.replace("<", "%3C").replace(">", "%3E").replace("\n", "")
                lines.append(f"- [{escape(source['label'])}](<{url}>) — {escape(source['role'])}")
        lines += ["", "Evidence checklist:", ""] + [f"- [ ] {task['question']}" for task in plan["checklist"]]
        lines += ["", "For each finding record: filing URL, publication date, period, note/page, currency/units and unresolved questions.",
                  "Do not enter zero for an undisclosed amount or treat ‘not found’ as ‘no risk’.", ""]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
