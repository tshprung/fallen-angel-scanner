"""Bounded primary filing excerpts supplied to the independent AI reviewer."""

import re

from filing_contents import DocumentClient, extract_content, valid_document_url
from sec_filings import SourceUnavailable

MAX_DOCUMENTS = 6


def identity(url):
    match = re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/data/(\d+)/(\d{18})/([A-Za-z0-9_.-]+\.html?)", url)
    if not match:
        return None
    cik, accession, _ = match.groups()
    accession = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"
    return (cik, accession) if valid_document_url(url, cik, accession) else None


def primary_packet(context, retrieved, client=None):
    # Only the issuer established by existing scanner metadata. Model URLs cannot
    # authorize another host, issuer, redirect, credential, PDF or arbitrary path.
    known = [identity(url) for url in context.get("source_urls", [])]
    issuers = {row[0] for row in known if row}
    result = {"documents": [], "failures": [], "notice":
              "Actual retrieved filing excerpts; partial text, not a complete audit. Missing excerpts are unknown."}
    if len(issuers) != 1:
        return result
    cik = next(iter(issuers))
    metadata_by_url = dict(context.get("source_metadata", {}))
    queue = list(dict.fromkeys(context.get("source_urls", []) + sorted(retrieved)))
    seen = set()
    client = client or DocumentClient()
    attempts = 0
    while queue and attempts < MAX_DOCUMENTS:
        url = queue.pop(0)
        document_id = identity(url)
        if url in seen or not document_id or document_id[0] != cik:
            continue
        seen.add(url)
        attempts += 1
        metadata = metadata_by_url.get(url) or {}
        document = {"url": url, "accessionNumber": document_id[1], "form": "PRIMARY",
                    "filingDate": metadata.get("published_at")}
        try:
            body, retrieved_at = client.get(document, cik)
            parsed = extract_content(body, document, cik, include_text=True)
            result["documents"].append({key: parsed[key] for key in
                ("url", "sha256", "filingDate", "visible_characters", "text_blocks", "text_is_partial")})
            result["documents"][-1]["retrieved_at"] = retrieved_at
            # Read earnings/financing exhibits with their filing, inside the same
            # six-document total limit; never treat their links as fetched content.
            exhibits = parsed["exhibit_links"][:2]
            for exhibit in exhibits:
                if exhibit.get("filingDate"):
                    metadata_by_url.setdefault(exhibit["url"], {"published_at": exhibit["filingDate"]})
            queue = [row["url"] for row in exhibits if row["url"] not in seen] + queue
        except (SourceUnavailable, ValueError, KeyError, TypeError):
            result["failures"].append({"url": url, "error": "PRIMARY_CONTENT_UNAVAILABLE"})
    return result


if __name__ == "__main__":
    # Public-source smoke check only: no OpenAI request, email or admission writes.
    import json
    from pathlib import Path
    import ai_research as ai
    report = json.loads(Path("ai_research.json").read_text(encoding="utf-8"))
    saved = json.loads(Path("research_report.json").read_text(encoding="utf-8"))
    audit = {row["ticker"]: row for row in saved["candidates"]}
    tickers = [row["ticker"] for row in report.get("failures", [])] or report.get("companies_attempted_today", [])
    results = []
    client = DocumentClient()
    for ticker in list(dict.fromkeys(tickers))[:3]:
        if ticker not in audit:
            continue
        item = audit[ticker]
        context = {"source_urls": ai.source_urls(item), "source_metadata": ai.source_metadata(item)}
        packet = primary_packet(context, set(), client)
        known = {row[0] for row in (identity(url) for url in context["source_urls"]) if row}
        status = "NOT_COVERED" if len(known) != 1 else "READY" if len(packet["documents"]) >= 2 else "INSUFFICIENT_CONTENT"
        results.append({"ticker": ticker, "status": status, "packet": packet})
        print(f"{ticker}: {status}; actual filing bodies: {len(packet['documents'])}; unavailable: {len(packet['failures'])}", flush=True)
    Path("ai_source_probe.json").write_text(json.dumps({"scope": "public_sources_only_no_openai_no_email", "results": results}, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1 if any(row["status"] == "INSUFFICIENT_CONTENT" for row in results) else 0)
