"""Inspectable research output and escaped financial evidence in email."""

from datetime import datetime, timezone
from html import escape
import json
import math
from pathlib import Path

from filing_review import write_filing_queue, filing_links_html
from sec_filings import filing_check_lines
from recovery_cases import RISK_TOPICS, write_recovery_queue
from filing_contents import write_content_report


def clean(value):
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(item) for item in value]
    if hasattr(value, "item"):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_research_report(audit, selected, prefix="research_report", scope=None):
    data = clean({"generated_at": datetime.now(timezone.utc).isoformat(),
                  "selected_tickers": [stock["ticker"] for stock in selected],
                  "documented_12m_tickers": [stock["ticker"] for stock in selected if (stock.get("goal_fit") or {}).get("status") == "DOCUMENTED_12M_CASE"],
                  "research_watch_tickers": [stock["ticker"] for stock in selected if (stock.get("goal_fit") or {}).get("status") != "DOCUMENTED_12M_CASE"],
                  "scan_scope": scope or {"type": "unspecified"},
                  "candidates": audit,
                  "notice": "Research screens and illustrative sensitivities; no guaranteed return or survival probability"})
    Path(f"{prefix}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Financial research report", "", data["notice"], "",
             f"Generated: {data['generated_at']}", "",
             f"Scope: {data['scan_scope'].get('type')}; symbols: {', '.join(data['scan_scope'].get('symbols', [])) or 'configured universe / see run logs'}.", "",
             f"Selected for research: {', '.join(data['selected_tickers']) or 'none'}.", "",
             f"Documented conditional 12-month cases: {', '.join(data['documented_12m_tickers']) or 'none'}. Other selections are research watches.", "",
             "| Ticker | Decision | Goal evidence | Solvency | Generic base sensitivity | Generic bull sensitivity | Main reason |",
             "|---|---|---|---|---:|---:|---|"]
    def text(value):
        return str(value).replace("|", "/").replace("\n", " ")
    coverage = data["scan_scope"].get("stage1_coverage")
    if coverage:
        lines[8:8] = [f"Stage 1 completed: {coverage['completed']}; processed {coverage['processed_count']}/{coverage['requested_count']}; quote responses {coverage['quote_successes']}; histories checked {coverage['histories_checked']}; recorded data gaps {len(coverage['data_gaps'])}.", "", coverage["notice"], ""]
    if data["scan_scope"].get("filing_content_collection"):
        lines[8:8] = [f"Filing content collection: {data['scan_scope']['filing_content_collection']}. Collection completion does not clear financial risks; inspect each document's status.", ""]
    health = data["scan_scope"].get("provider_health")
    if health:
        lines[8:8] = [f"Provider health: {health['status']}; systemic failure: {health['systemic_failure']}; company analysis errors: {health['company_analysis_errors']}/{health['company_candidates']}.", "", health["notice"], ""]
    for item in audit:
        solvency = item.get("solvency") or {}
        valuation = item.get("valuation") or {}
        cases = valuation.get("cases") or {}
        def upside(name):
            value = cases.get(name, {}).get("return_pct")
            return f"{value:+.1f}%" if value is not None else "unavailable"
        reasons = solvency.get("flags", []) + solvency.get("missing", []) + solvency.get("review", [])
        reason = item.get("reason") or (reasons[0] if reasons else "")
        lines.append(f"| {text(item['ticker'])} | {text(item.get('decision', 'not_selected'))} | {(item.get('goal_fit') or {}).get('status', 'not_evaluated')} | {solvency.get('status', 'not_evaluated')} | {upside('base')} | {upside('bull')} | {text(reason)} |")
    for item in audit:
        check = item.get("official_filing_check")
        if check:
            lines += ["", f"## Official filing evidence: {text(item['ticker'])}", ""] + filing_check_lines(check)
    lines += ["", "Full statement period ends, row labels, missing fields, assumptions and exclusions are in research_report.json.",
              "A REVIEW status commonly means the 13–24 month contractual debt schedule still needs filing review. UNVERIFIED and SPECIALIST_REVIEW candidates cannot enter the ordinary-company shortlist.",
              "An empty shortlist is a valid result. Scenario assumptions are configurable in research_policy.json and are not empirically calibrated predictions."]
    Path(f"{prefix}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_filing_queue(audit, Path(prefix).with_name("filing_review.md"))
    write_recovery_queue(audit, Path(prefix).with_name("recovery_review.md"))
    write_content_report(audit, Path(prefix).with_name("filing_contents.md"))
    return data


def candidate_needs_review(stock):
    return (stock.get("catalyst_status") == "WATCH"
            or (bool(stock.get("goal_fit")) and stock["goal_fit"].get("status") != "DOCUMENTED_12M_CASE")
            or (stock.get("official_filing_check") or {}).get("status") == "NOT_COVERED"
            or stock.get("solvency_status") in ("REVIEW", "UNVERIFIED", "SPECIALIST_REVIEW")
            or stock.get("risk_score_raw", stock.get("risk_score", 10)) >= 4)


def filing_review_summary_html(audit):
    held = [item for item in audit if item.get("decision") in {"event_review", "filing_review", "filing_unverified"}]
    if not held:
        return ""
    rows = []
    for item in held:
        check = item.get("official_filing_check") or {}
        documents = ([check["latest_financial_report"]] if check.get("latest_financial_report") else []) + check.get("event_filings", [])
        links = [f'<a href="{escape(document["url"], quote=True)}">{escape(document["form"])} {escape(document["filingDate"])}</a>' for document in documents]
        for source in (item.get("review_hold") or {}).get("sources", []):
            links.append(f'<a href="{escape(source["url"], quote=True)}">Disclosure {escape(source["published_at"])}</a>')
        notes = (item.get("review_hold") or {}).get("review_notes", [])
        findings = ("<ul>" + "".join(f'<li>{escape(note["finding"])} <a href="{escape(note["source_url"], quote=True)}">Source</a></li>' for note in notes) + "</ul>") if notes else ""
        content = item.get("filing_content_review") or {}
        content_note = f" Content index: {escape(content['status'])}; contents still require interpretation." if content else ""
        rows.append(f"<li><strong>{escape(item['ticker'])}</strong>: {escape(item.get('reason', 'Review required'))}.{content_note} {'; '.join(links)}{findings}</li>")
    return ("<h2>Held for filing review</h2><p>These names did not qualify for selection. "
            "An unavailable source is unverified; it is not an empty event search. "
            "Filing metadata does not verify document contents.</p><ul>" + "".join(rows) + "</ul>")


def financial_detail_html(stock):
    solvency = stock.get("solvency")
    valuation = stock.get("valuation")
    if not solvency and not valuation:
        return ""
    evidence = stock.get("financial_evidence") or {}
    parts = ["<div><h4>Financial evidence and valuation sensitivities</h4>"]
    fit = stock.get("goal_fit")
    if fit:
        parts.append(f"<h4>Twelve-month goal: {escape(fit['status'])}</h4>")
        signal = stock.get("price_dislocation") or {}
        fall, age = signal.get("drop_recent_peak_pct"), signal.get("recent_peak_age_sessions")
        if fall is not None and age is not None:
            parts.append(f"<p>Decline from recent peak: {fall:.1f}%; peak {age} trading sessions ago.</p>")
        if fit["missing"]:
            parts.append("<p>Research watch; the one-year doubling thesis is unverified.</p><ul>" + "".join(f"<li>{escape(message)}</li>" for message in fit["missing"]) + "</ul>")
        required = fit.get("doubling_requirements")
        if required:
            parts.append(f"<p>What 2x requires: at unchanged normalized cash flow, an equity cash-flow multiple of {required['equity_fcf_multiple_at_unchanged_normalized_fcf']:.1f}x, including generic assumed dilution. This is reverse arithmetic, not a forecast.</p>")
        if fit["status"] == "DOCUMENTED_12M_CASE":
            record = fit["research_record"]
            catalyst = record["catalyst"]
            parts.append(f"<p>Conditional catalyst: {escape(catalyst['finding'])}. Milestone: {escape(catalyst['metric'])} by {escape(catalyst['expected_by'])}. Thesis fails if: {escape(catalyst['invalidation'])}. Valuation date: {escape(record['target_by'])}.</p>")
            parts.append("<table><tr><th>Company-specific case</th><th>Price</th><th>Return</th></tr>" + "".join(
                f"<tr><td>{escape(name)}</td><td>{case['price']:.2f} {escape(stock['currency'])}</td><td>{case['return_pct']:+.1f}%</td></tr>" for name, case in fit["cases"].items()) + "</table>")
            blocks = [record["cause"], catalyst, record["valuation"]] + [record["risk_reviews"][name] for name in RISK_TOPICS] + [record["valuation"]["cases"][name] for name in ("bear", "base", "recovery")]
            sources = {source["url"]: source["published_at"] for block in blocks for source in block.get("sources", [])}
            parts.append("<p>Research sources: " + "; ".join(f'<a href="{escape(url, quote=True)}">Disclosure {escape(date)}</a>' for url, date in sources.items()) + "</p>")
        parts.append(f"<p>{escape(fit['notice'])}</p>")
    content = stock.get("filing_content_review")
    if content:
        parts.append(f"<p>Filing-content index: {escape(content['status'])}. {escape(content['notice'])}</p>")
    if solvency:
        parts.append(f"<p><strong>Solvency screen: {escape(solvency['status'])}</strong> (not a survival guarantee)</p>")
        messages = solvency["flags"] + solvency["missing"] + solvency["review"]
        if messages:
            parts.append("<ul>" + "".join(f"<li>{escape(message)}</li>" for message in messages) + "</ul>")
        metrics = solvency.get("metrics", {})
        labels = {"interest_coverage": "EBIT / interest (x)", "debt_equity": "Debt / equity (x)",
                  "net_debt_ebitda": "Net debt / EBITDA (x)", "current_debt_coverage": "Current-debt coverage (x)",
                  "cash_runway_months": "Cash runway (months)", "current_ratio": "Current ratio (x)",
                  "fcf_after_interest_buffer": f"Annual cash-flow proxy after buffer ({evidence.get('financial_currency')})"}
        parts.append("<p>" + " | ".join(f"{escape(labels.get(name, name))}: {value:,.2f}" for name, value in metrics.items()) + "</p>")
    dates = []
    for name in ("balance", "cashflow", "income"):
        block = evidence.get(name, {})
        if block:
            dates.append(f"{name}: {block.get('asof') or 'unavailable'} ({block.get('basis')})")
    parts.append("<p>Statement period ends: " + escape("; ".join(dates)) + ". Provider numbers are not reconciled to filing contents.</p>")
    check = stock.get("official_filing_check")
    if check:
        parts.append(f"<p><strong>Official filing check: {escape(check['status'])}</strong>. {escape(check['notice'])}</p>")
        parts.append("<ul>" + "".join(f"<li>{escape(finding)}</li>" for finding in check.get("findings", [])) + "</ul>")
        document = check.get("latest_financial_report")
        if document:
            parts.append(f'<p><a href="{escape(document["url"], quote=True)}">Latest SEC {escape(document["form"])}: period {escape(document["reportDate"])}; filed {escape(document["filingDate"])}</a></p>')
    if valuation and valuation.get("status") == "SENSITIVITY":
        parts.append(f"<p>{escape(valuation['description'])}. Assumed share dilution: {valuation['assumed_share_dilution']:.0%}. No probabilities assigned.</p>")
        parts.append("<table><tr><th>Case</th><th>FCF factor</th><th>Equity FCF multiple</th><th>Price (quote units)</th><th>Return</th></tr>")
        for name, case in valuation["cases"].items():
            parts.append(f"<tr><td>{escape(name)}</td><td>{case['fcf_factor']:.2f}</td><td>{case['equity_fcf_multiple']:.1f}x</td><td>{case['price']:.2f} {escape(stock['currency'])}</td><td>{case['return_pct']:+.1f}%</td></tr>")
        parts.append("</table><p>A bull case at 2× is a sensitivity flag, not a one-year forecast.</p>")
    elif valuation:
        parts.append("<p>Valuation unavailable: " + escape(valuation.get("reason") or "insufficient data") + "</p>")
    parts.append(filing_links_html(stock.get("filing_review")))
    parts.append(f"<p>Research policy: {escape(evidence.get('policy_id') or '')}</p></div>")
    return "".join(parts)
