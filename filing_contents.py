"""Bounded SEC filing-content evidence collection; never automatic risk clearance."""

from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import unquote, urljoin, urlsplit

from lxml import html, etree
import requests

from sec_filings import SecClient, SourceUnavailable, check_sec_filings, utc

MAX_BYTES = 12 * 1024 * 1024
NOTICE = ("Content index for research, not a verified maturity schedule or a solvency opinion. "
          "Matches may describe hypothetical risks, negations or boilerplate. Amounts retain raw units; "
          "no amounts are summed, annualized or treated as unrestricted liquidity. No match does not mean no risk. "
          "This collector never clears a hold or upgrades an investment case.")
TOPICS = {
    "liquidity": r"\bliquidity\b|unrestricted cash|cash equivalents|undrawn|revolving credit|available borrowings",
    "debt_maturities": r"\bmaturit\w*\b|\bmatures?\b|\bdue (?:in )?20\d{2}\b|repayment|principal amount|redemption",
    "covenants": r"\bcovenant\w*\b|coverage ratio|debt.to.capitalization|\bdefault\w*\b|non.compliance",
    "going_concern": r"going concern|substantial doubt|bankruptcy|insolvency",
    "listing_and_transactions": r"delist\w*|minimum bid|listing standards|reverse stock split|merger|tender offer|exchange compliance",
    "dilution": r"convertible|capped.call|dilut\w*|stock.based compensation|issuance of (?:common|shares)",
    "outlook": r"\bguidance\b|\boutlook\b|\bforecast\w*\b|profit warning",
}
TOKENS = re.compile(r"(?:\$|USD\s*)\s*\d[\d,.]*(?:\s*(?:million|billion|thousand))?"
    r"|\b\d[\d,.]*\s*(?:million|billion|thousand|%|to 1\.00)"
    r"|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2}", re.I)


def valid_document_url(url, cik, accession):
    try:
        parts = urlsplit(url)
        prefix = f"/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
        name = unquote(parts.path[len(prefix):]) if parts.path.startswith(prefix) else ""
        return (parts.scheme == "https" and parts.netloc == "www.sec.gov" and not parts.query and not parts.fragment
                and bool(re.fullmatch(r"[A-Za-z0-9_.-]+\.html?", name)) and ".." not in name
                and bool(re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession)))
    except (ValueError, TypeError, AttributeError):
        return False


class DocumentClient:
    def __init__(self, sec_client=None):
        self.sec = sec_client or SecClient()
        self.memory = {}

    def get(self, document, cik):
        url, accession = document["url"], document["accessionNumber"]
        if not valid_document_url(url, cik, accession):
            raise SourceUnavailable("Invalid SEC filing document identity")
        if url in self.memory:
            value = self.memory[url]
            if isinstance(value, SourceUnavailable):
                raise value
            return value
        now = utc()
        path = self.sec.cache_dir / ("document-" + hashlib.sha256(url.encode()).hexdigest() + ".json")
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            age = now - utc(cached["retrieved_at"])
            body = cached["body"]
            if cached["url"] == url and timedelta(0) <= age <= timedelta(days=7) and isinstance(body, str) and len(body.encode()) <= MAX_BYTES:
                self.memory[url] = (body, cached["retrieved_at"])
                return self.memory[url]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        failure = SourceUnavailable("Filing document request failed")
        for attempt in range(2):
            time.sleep(max(0, .55 - (time.monotonic() - self.sec.last_request)))
            self.sec.last_request = time.monotonic()
            response = None
            try:
                response = self.sec.session.get(url, headers={"User-Agent": self.sec.user_agent,
                    "Accept": "text/html"}, timeout=(5, 20), stream=True, allow_redirects=False)
                if response.status_code != 200:
                    failure = SourceUnavailable(f"Filing document HTTP {response.status_code}")
                    if response.status_code not in {429, 500, 502, 503, 504}:
                        break
                else:
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise SourceUnavailable("Filing document exceeds 12 MiB content limit")
                        chunks.append(chunk)
                    body = b"".join(chunks).decode("utf-8-sig", errors="replace")
                    if re.search(r"request rate threshold exceeded|your request originates from an undeclared automated tool|<title>access denied", body, re.I):
                        raise SourceUnavailable("SEC returned an access/rate-limit page instead of a filing")
                    stamp = utc().isoformat()
                    self.memory[url] = (body, stamp)
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        temp = path.with_suffix(".tmp")
                        temp.write_text(json.dumps({"url": url, "retrieved_at": stamp, "body": body}), encoding="utf-8")
                        temp.replace(path)
                    except OSError:
                        pass
                    return body, stamp
            except SourceUnavailable as exc:
                failure = exc
                break
            except requests.RequestException as exc:
                failure = SourceUnavailable(f"Filing document network error ({type(exc).__name__})")
                if isinstance(exc, (requests.exceptions.SSLError, requests.exceptions.InvalidHeader)):
                    break
            except UnicodeError:
                failure = SourceUnavailable("Filing document header encoding is invalid")
                break
            finally:
                if response is not None:
                    response.close()
            if attempt == 0:
                time.sleep(1)
        self.memory[url] = failure
        raise failure


def normalized_text(element):
    return " ".join(element.text_content().split())


def extract_content(body, document, cik):
    if not isinstance(body, str):
        raise SourceUnavailable("Filing body is not text")
    if len(body.encode()) > MAX_BYTES:
        raise SourceUnavailable("Filing document exceeds content limit")
    try:
        # SEC inline-XBRL commonly includes an XML encoding declaration.
        # lxml rejects declarations in Unicode input, so parse decoded UTF-8 as bytes.
        tree = html.fromstring(body.encode("utf-8"), parser=html.HTMLParser(encoding="utf-8", no_network=True, recover=True))
    except (ValueError, TypeError, etree.ParserError, etree.XMLSyntaxError) as exc:
        raise SourceUnavailable("Filing HTML could not be parsed") from exc
    for element in list(tree.iter()):
        if not isinstance(element.tag, str):
            continue  # Comments/processing instructions have no HTML attributes.
        tag = str(element.tag).lower().split("}")[-1]
        style = re.sub(r"\s+", "", (element.get("style") or "").lower())
        if (tag in {"script", "style", "head", "ix:hidden"} or tag.endswith(":hidden")
                or element.get("hidden") is not None or element.get("aria-hidden") == "true" or "display:none" in style):
            if element.getparent() is not None:
                element.drop_tree()
    visible = normalized_text(tree)
    if len(visible) < 120:
        raise SourceUnavailable("Too little visible filing content; no clearance inferred")
    # Keep table rows together; avoid counting each nested cell paragraph again.
    elements = tree.xpath("//p[not(ancestor::table) and not(ancestor::p)] | //table[not(ancestor::table)] | //div[not(descendant::p) and not(descendant::table) and not(ancestor::table) and not(descendant::div)]")
    blocks = [(element, normalized_text(element)) for element in elements if normalized_text(element)]
    if not blocks:
        blocks = [(tree, visible)]
    topics = {name: {"matched_blocks": 0, "locations": []} for name in TOPICS}
    for index, (element, text) in enumerate(blocks):
        for name, pattern in TOPICS.items():
            hits = sorted(set(match.group().lower() for match in re.finditer(pattern, text, re.I)))
            if not hits:
                continue
            topic = topics[name]
            topic["matched_blocks"] += 1
            if len(topic["locations"]) < 3:
                # Tokens are raw facts, not a complete table or a maturity ladder.
                match = re.search(pattern, text, re.I)
                context = text[max(0, match.start() - 120):match.end() + 500]
                topic["locations"].append({"block": index, "kind": "table" if element.tag == "table" else "paragraph",
                    "terms": hits[:6], "raw_amount_date_tokens": list(dict.fromkeys(TOKENS.findall(context)))[:12]})
    exhibits = []
    for anchor in tree.xpath("//a[@href]"):
        label = normalized_text(anchor)
        url = urljoin(document["url"], anchor.get("href"))
        if (re.search(r"\b(?:99|10)\.\d|exhibit|ex[-_]?99|ex[-_]?10", label + " " + url, re.I)
                and url != document["url"] and valid_document_url(url, cik, document["accessionNumber"])
                and url not in [item["url"] for item in exhibits]):
            exhibits.append({"url": url, "accessionNumber": document["accessionNumber"],
                "filingDate": document.get("filingDate"), "form": "EXHIBIT"})
            if len(exhibits) == 8:
                break
    return {"status": "INDEXED_FOR_REVIEW", "url": document["url"], "form": document["form"],
            "accessionNumber": document["accessionNumber"], "filingDate": document.get("filingDate"),
            "sha256": hashlib.sha256(body.encode()).hexdigest(), "visible_characters": len(visible),
            "topics": topics, "exhibit_links": exhibits, "notice": NOTICE}


def collect_filing_contents(check, client=None, max_primary=3, max_exhibits=1):
    result = {"status": "UNVERIFIED", "checked_at": utc().isoformat(), "documents": [], "notice": NOTICE,
              "document_budget": {"primary": max_primary, "exhibits": max_exhibits}, "deferred_documents": 0}
    if check and check.get("status") == "NOT_COVERED":
        return dict(result, status="NOT_COVERED", reason="Use local-regulator/issuer documents; this collector covers SEC filings only")
    if not check or not check.get("cik"):
        result["reason"] = "Verified SEC issuer/document metadata unavailable"
        return result
    client = client or DocumentClient()
    primary = [check.get("latest_financial_report"), check.get("latest_annual_report")]
    primary += [row for row in check.get("event_filings", []) if row["form"] in {"8-K", "8-K/A", "6-K", "6-K/A"}]
    primary = list({row["url"]: row for row in primary if row}.values())
    deferred = {row["url"] for row in primary[max_primary:]}
    queue = primary[:max_primary]
    used_exhibits = 0
    for document in queue:
        try:
            body, retrieved_at = client.get(document, check["cik"])
            parsed = extract_content(body, document, check["cik"])
            parsed["retrieved_at"] = retrieved_at
            result["documents"].append(parsed)
            for exhibit in parsed["exhibit_links"]:
                if exhibit["url"] in [row["url"] for row in queue]:
                    continue
                if used_exhibits < max_exhibits:
                    queue.append(exhibit)
                    used_exhibits += 1
                else:
                    deferred.add(exhibit["url"])
        except (SourceUnavailable, ValueError, KeyError, TypeError) as exc:
            reason = str(exc) if isinstance(exc, SourceUnavailable) else "Malformed filing content metadata"
            result["documents"].append({"status": "UNVERIFIED", "url": document.get("url"), "reason": reason})
    result["deferred_documents"] = len(deferred - {row["url"] for row in queue})
    indexed = sum(document["status"] == "INDEXED_FOR_REVIEW" for document in result["documents"])
    if indexed:
        result["status"] = "PARTIAL" if indexed < len(result["documents"]) or result["deferred_documents"] else "INDEXED_FOR_REVIEW"
    else:
        result["reason"] = "No filing body could be indexed; missing content is not absence of risk"
    return result


def enrich_research_audit(audit, selected, sec_client=None, max_issuers=12, rotation_day=None):
    sec_client = sec_client or SecClient()
    client = DocumentClient(sec_client)
    by_ticker = {stock["ticker"]: stock for stock in selected}
    def upside_near_miss(item):
        # Research a financially covered near miss without bypassing its risk
        # exclusion. Illustrative upside alone cannot prioritize a hard failure.
        return (item.get("decision") == "risk_excluded"
                and (item.get("solvency") or {}).get("status") == "REVIEW"
                and (item.get("valuation") or {}).get("plausible_upside_screen") is True)

    eligible = [item for item in audit if item.get("decision") in
                {"selected", "event_review", "filing_review", "filing_unverified"}
                or upside_near_miss(item)]
    def priority(item):
        if item["ticker"] in by_ticker or item.get("decision") == "selected":
            return 0
        if upside_near_miss(item):
            return 1
        if item.get("review_hold"):
            return 2
        return 3
    eligible.sort(key=priority)
    urgent = [item for item in eligible if priority(item) < 3]
    routine = sorted((item for item in eligible if priority(item) == 3), key=lambda item: item["ticker"])
    slots = max(0, max_issuers - len(urgent))
    if slots and len(routine) > slots:
        # Advance by a full batch each UTC day, so a stable routine queue is
        # covered instead of repeatedly indexing only its first issuers.
        day = rotation_day or utc().date()
        offset = (day.toordinal() * slots) % len(routine)
        routine = routine[offset:] + routine[:offset]
    eligible = urgent + routine
    for index, item in enumerate(eligible):
        if index >= max_issuers:
            review = {"status": "DEFERRED_BUDGET", "documents": [], "notice": NOTICE,
                      "reason": f"Content collection limited to {max_issuers} issuers per scan; routine queue rotates daily in UTC"}
        else:
            check = item.get("official_filing_check")
            if not check:
                check = check_sec_filings(item["ticker"], item.get("financial_evidence") or {}, client=sec_client)
                item["official_filing_check"] = check
            review = collect_filing_contents(check, client)
        item["filing_content_review"] = review
        if item["ticker"] in by_ticker:
            by_ticker[item["ticker"]]["filing_content_review"] = review


def write_content_report(audit, path):
    lines = ["# Filing-content evidence index", "", NOTICE, "",
             "Amounts/dates below are raw search tokens, not verified obligations or funding. Block indices refer to the parser's visible paragraph/table sequence, not printed page numbers.", ""]
    checked = [item for item in audit if item.get("filing_content_review")]
    if not checked:
        lines += ["No filing-content review is attached yet; see research_report.json scan_scope for collection status.", ""]
    for item in checked:
        review = item["filing_content_review"]
        lines += [f"## {item['ticker']}: {review['status']}", ""]
        if review.get("reason"):
            lines += [review["reason"], ""]
        lines += [f"Deferred documents: {review.get('deferred_documents', 'not evaluated')}.", ""]
        for document in review["documents"]:
            lines += [f"Source: <{document['url']}> — {document['status']}", ""]
            if document.get("reason"):
                lines += [document["reason"], ""]
                continue
            lines += [f"Retrieved {document['retrieved_at']}; decoded-content SHA-256 {document['sha256']}.", ""]
            for topic, evidence in document["topics"].items():
                lines.append(f"- {topic}: {evidence['matched_blocks']} matching blocks; absence of matches is not risk clearance.")
                for location in evidence["locations"]:
                    tokens = "; ".join(location["raw_amount_date_tokens"]) or "no raw amounts/dates in search context"
                    lines.append(f"  - {location['kind']} block {location['block']}: {tokens}")
            lines += [""]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Probe latest SEC filing bodies without email, paper selections or risk upgrades")
    parser.add_argument("--metadata", default="sec_source_probe.json")
    parser.add_argument("--output", default="filing_content_probe.json")
    args = parser.parse_args()
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    client = DocumentClient()
    audits = []
    for check in metadata["checks"]:
        review = collect_filing_contents(check, client, max_primary=1, max_exhibits=0)
        audits.append({"ticker": check["ticker"], "filing_content_review": review})
        indexed = sum(doc["status"] == "INDEXED_FOR_REVIEW" for doc in review["documents"])
        print(f"{check['ticker']}: latest-primary bodies indexed: {indexed}; {review['status']}")
        for document in review["documents"]:
            if document.get("reason"):
                print(f"  {document['reason']}")
    Path(args.output).write_text(json.dumps({"scope": "latest_primary_filing_content_probe_not_a_risk_clearance", "candidates": audits}, indent=2) + "\n", encoding="utf-8")
    write_content_report(audits, Path(args.output).with_suffix(".md"))
    raise SystemExit(0 if all(any(doc["status"] == "INDEXED_FOR_REVIEW" for doc in item["filing_content_review"]["documents"]) for item in audits) else 1)
