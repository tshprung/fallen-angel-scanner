"""SEC publication/event metadata checks, not interpretation of filing contents."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import quote

import requests

SEC_MAPPING = "https://www.sec.gov/files/company_tickers_exchange.json"
NOTICE = ("SEC metadata only; filing bodies, exhibits, covenant terms and recovery catalysts "
          "are not automatically verified. No flagged filing does not establish absence of risk. "
          "Event lookback: 365 days for merger forms, 180 days for current reports.")
PERIODIC = {"10-K", "10-Q", "20-F", "40-F"}
MERGER = {"425", "S-4", "S-4/A", "F-4", "F-4/A", "DEFM14A", "PREM14A"}
MATERIAL_ITEMS = {
    "1.01": "material agreement", "1.02": "agreement termination", "1.03": "bankruptcy/receivership",
    "2.01": "acquisition/disposal", "2.03": "new financial obligation", "2.04": "repayment acceleration trigger",
    "2.05": "restructuring costs", "2.06": "impairment", "3.01": "listing/compliance notice",
    "3.02": "unregistered securities sale", "4.01": "auditor change", "4.02": "financial-statement non-reliance",
}


class SourceUnavailable(ValueError):
    pass


def utc(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def symbol(value):
    return str(value).upper().replace(".", "-")


class SecClient:
    """Bounded requests; fresh cache only. Access errors never imply clearance."""

    def __init__(self, cache_dir=None, session=None, now=None):
        self.now = utc(now)
        self.fixed_now = now is not None
        self.cache_dir = Path(cache_dir or os.getenv("SEC_CACHE_DIR", ".sec-cache"))
        contact = os.getenv("SEC_CONTACT_EMAIL") or os.getenv("SENDER_EMAIL")
        identity = contact or "https://github.com/tshprung/fallen-angel-scanner"
        # Secrets copied from a form can retain a trailing newline. Collapse
        # whitespace before putting contact identification in an HTTP header.
        self.user_agent = " ".join((os.getenv("SEC_USER_AGENT") or f"FallenAngelScanner/1.0 ({identity.strip()})").split())
        self.session = session or requests.Session()
        self.memory = {}
        self.last_request = 0.0

    def get_json(self, url):
        if not (url == SEC_MAPPING or re.fullmatch(
                r"https://data\.sec\.gov/submissions/CIK\d{10}(?:-submissions-\d{3})?\.json", url)):
            raise SourceUnavailable("Unrecognized SEC endpoint")
        now = self.now if self.fixed_now else utc()
        ttl = timedelta(days=7) if url == SEC_MAPPING else timedelta(minutes=15)
        if url in self.memory:
            value = self.memory[url]
            if isinstance(value, SourceUnavailable):
                raise value
            if timedelta(0) <= now - utc(value[1]) <= ttl:
                return value
            del self.memory[url]
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            age = now - utc(cached["retrieved_at"])
            if cached["url"] == url and timedelta(0) <= age <= ttl:
                result = (cached["data"], cached["retrieved_at"])
                self.memory[url] = result
                return result
        except (OSError, ValueError, KeyError, TypeError):
            pass
        failure = SourceUnavailable("SEC request failed")
        for attempt in range(3):
            time.sleep(max(0, .55 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = self.session.get(url, headers={"User-Agent": self.user_agent,
                    "Accept": "application/json"}, timeout=(5, 20), allow_redirects=False)
                if response.status_code != 200:
                    failure = SourceUnavailable(f"SEC HTTP {response.status_code}")
                    if response.status_code not in {429, 500, 502, 503, 504}:
                        break
                else:
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ValueError("Expected JSON object")
                    stamp = (now if self.fixed_now else utc()).isoformat()
                    self.memory[url] = (payload, stamp)
                    # Caching is optional; a disk problem must not discard fetched evidence.
                    try:
                        self.cache_dir.mkdir(parents=True, exist_ok=True)
                        temporary = path.with_suffix(".tmp")
                        temporary.write_text(json.dumps({"url": url, "retrieved_at": stamp, "data": payload}), encoding="utf-8")
                        temporary.replace(path)
                    except OSError:
                        pass
                    return payload, stamp
            except requests.RequestException as exc:
                # Exception text can contain headers/contact information. Keep
                # only its class so diagnostics never disclose the User-Agent.
                failure = SourceUnavailable(f"SEC network request failed ({type(exc).__name__})")
                if isinstance(exc, (requests.exceptions.SSLError, requests.exceptions.InvalidHeader)):
                    break
            except UnicodeError:
                failure = SourceUnavailable("SEC contact header encoding is invalid")
                break
            except ValueError:
                failure = SourceUnavailable("SEC returned malformed JSON")
                break
            if attempt < 2:
                time.sleep(2 ** attempt)
        self.memory[url] = failure
        raise failure


def load_filing_resolutions(path=None):
    """Only accession-specific, documented reviews can resolve an event flag."""
    records = json.loads(Path(path or Path(__file__).with_name("sec_filing_reviews.json")).read_text(encoding="utf-8"))
    if not isinstance(records, dict):
        raise ValueError("SEC filing reviews must be an object")
    for key, record in records.items():
        if (not re.fullmatch(r"\d{10}:\d{10}-\d{2}-\d{6}", key) or not record.get("finding")
                or not record.get("reviewed_at") or not record.get("source_url")):
            raise ValueError(f"Incomplete accession-specific review: {key}")
        utc(record["reviewed_at"])
    return records


def filing_rows(block, cik):
    required = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    if not isinstance(block, dict) or any(not isinstance(block.get(key), list) for key in required):
        raise SourceUnavailable("Incomplete SEC filing arrays")
    length = len(block["form"])
    if any(len(block[key]) != length for key in required):
        raise SourceUnavailable("Misaligned SEC filing arrays")
    for key in ("items", "acceptanceDateTime"):
        if key in block and (not isinstance(block[key], list) or len(block[key]) != length):
            raise SourceUnavailable("Misaligned SEC optional filing arrays")
    rows = []
    for i in range(length):
        row = {key: block[key][i] for key in required}
        if row["form"] not in PERIODIC | MERGER | {name + "/A" for name in PERIODIC} | {"8-K", "8-K/A", "6-K", "6-K/A"}:
            continue
        accession, document = row["accessionNumber"], row["primaryDocument"]
        if (not isinstance(accession, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession)
                or not isinstance(document, str) or not document or "/" in document or "\\" in document):
            raise SourceUnavailable("Invalid SEC document identity")
        utc(row["filingDate"])
        if row["form"] in PERIODIC and not row["reportDate"]:
            raise SourceUnavailable("SEC financial report has no statement period")
        if row["reportDate"]:
            utc(row["reportDate"])
        row.update(items=block.get("items", [""] * length)[i],
                   accepted_at=block.get("acceptanceDateTime", [""] * length)[i],
                   url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{quote(document, safe='')}" )
        rows.append(row)
    return rows


def analyze_filings(cik, rows, evidence, now=None, resolutions=None):
    now = utc(now)
    resolutions = resolutions or {}
    rows = [row for row in rows if utc(row["filingDate"]).date() <= now.date()
            and (not row["accepted_at"] or utc(row["accepted_at"]) <= now)]
    rows.sort(key=lambda row: (row["filingDate"], row["accessionNumber"]), reverse=True)
    periodic = [row for row in rows if row["form"] in PERIODIC and row["reportDate"]]
    if not periodic:
        raise SourceUnavailable("No dated periodic financial report in covered SEC history")
    latest = max(periodic, key=lambda row: (row["reportDate"], row["filingDate"]))
    if utc(latest["reportDate"]).date() > now.date():
        raise SourceUnavailable("SEC financial report period is in the future")
    findings, documents = [], []
    for name in ("balance", "cashflow", "income"):
        asof = (evidence.get(name) or {}).get("asof")
        if not asof or utc(asof).date() < utc(latest["reportDate"]).date():
            findings.append(f"{name} evidence predates SEC {latest['form']} period {latest['reportDate']} (filed {latest['filingDate']})")
    for row in rows:
        days = (now.date() - utc(row["filingDate"]).date()).days
        form, reason = row["form"], None
        if form in MERGER and days <= 365:
            reason = "Merger/transaction filing requires current-status and valuation review"
        elif form in {name + "/A" for name in PERIODIC} and days <= 365:
            reason = "Amended financial report requires reconciliation"
        elif form in {"8-K", "8-K/A"} and days <= 180:
            items = set(re.findall(r"\b\d\.\d{2}\b", str(row["items"] or "")))
            labels = [MATERIAL_ITEMS[item] for item in sorted(items) if item in MATERIAL_ITEMS]
            if labels:
                reason = "Current-report items: " + ", ".join(labels)
            elif not items:
                reason = "Current-report items unavailable; contents require review"
            elif items & {"2.02", "7.01"} and row["filingDate"] > latest["filingDate"]:
                reason = "Results/outlook disclosure published after latest periodic financial filing"
        elif form in {"6-K", "6-K/A"} and days <= 180:
            reason = "Foreign-issuer current report needs results/event review"
        if reason:
            resolution = resolutions.get(f"{int(cik):010d}:{row['accessionNumber']}")
            reviewed = bool(resolution and resolution["source_url"] == row["url"]
                and utc(row["filingDate"]).date() <= utc(resolution["reviewed_at"]).date() <= now.date())
            documents.append(dict(row, review_reason=reason, resolution=resolution if reviewed else None))
            if not reviewed:
                findings.append(f"{form} filed {row['filingDate']}: {reason}")
    return {"status": "REVIEW_REQUIRED" if findings else "METADATA_CHECKED",
            "blocks_selection": bool(findings), "findings": findings,
            "latest_financial_report": latest, "event_filings": documents, "notice": NOTICE}


def check_sec_filings(ticker, evidence, client=None, now=None, resolutions=None):
    now = utc(now)
    result = {"checker_version": 1, "checked_at": now.isoformat(), "ticker": ticker, "notice": NOTICE}
    if ticker.upper().endswith((".L", ".DE", ".WA", ".TA")):
        return dict(result, status="NOT_COVERED", blocks_selection=False, findings=[
            "This listing needs its local regulator/issuer sources; the SEC checker does not cover it."])
    client = client or SecClient(now=now)
    try:
        mapping, mapping_at = client.get_json(SEC_MAPPING)
        fields = mapping["fields"]
        if not all(key in fields for key in ("cik", "ticker", "exchange")):
            raise SourceUnavailable("SEC ticker mapping schema is incomplete")
        entries = [dict(zip(fields, row)) for row in mapping["data"] if len(row) == len(fields)]
        matches = {int(row["cik"]) for row in entries if symbol(row["ticker"]) == symbol(ticker)}
        if len(matches) != 1:
            raise SourceUnavailable("SEC ticker-to-issuer mapping missing or ambiguous")
        cik = matches.pop()
        result.update(cik=f"{cik:010d}", mapping_retrieved_at=mapping_at)
        payload, retrieved_at = client.get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if int(payload["cik"]) != cik or symbol(ticker) not in {symbol(t) for t in payload["tickers"]}:
            raise SourceUnavailable("SEC submission identity does not match ticker mapping")
        result.update(issuer=payload["name"], submissions_retrieved_at=retrieved_at)
        rows = filing_rows(payload["filings"]["recent"], cik)
        cutoff = (now - timedelta(days=365)).date().isoformat()
        archives = [item for item in payload["filings"]["files"]
                    if item["filingTo"] >= cutoff and item["filingFrom"] <= now.date().isoformat()]
        if len(archives) > 4:
            raise SourceUnavailable("SEC history requires more than four archive pages; coverage incomplete")
        result["archive_sources"] = []
        for archive in archives:
            name = archive["name"]
            if not re.fullmatch(rf"CIK{cik:010d}-submissions-\d{{3}}\.json", name):
                raise SourceUnavailable("Invalid SEC archive name")
            url = "https://data.sec.gov/submissions/" + name
            block, stamp = client.get_json(url)
            rows.extend(filing_rows(block, cik))
            result["archive_sources"].append({"url": url, "retrieved_at": stamp})
        rows = list({row["accessionNumber"]: row for row in rows}.values())
        result.update(analyze_filings(cik, rows, evidence, now, resolutions))
    except (SourceUnavailable, ValueError, KeyError, TypeError, OverflowError) as exc:
        message = str(exc) if isinstance(exc, SourceUnavailable) else "Malformed SEC metadata or statement period"
        result.update(status="UNVERIFIED", blocks_selection=True, findings=[message])
    return result


def filing_check_lines(check):
    """Markdown also feeds plain review queues; preserve exact source identity."""
    if not check:
        return []
    lines = [f"Official filing check: {check['status']} (checked {check['checked_at']}).", "",
             check["notice"], ""]
    lines += [f"- {finding}" for finding in check.get("findings", [])]
    documents = ([check["latest_financial_report"]] if check.get("latest_financial_report") else []) + check.get("event_filings", [])
    for document in documents:
        label = f"{document['form']} filed {document['filingDate']} ({document['accessionNumber']})"
        state = " — documented review recorded" if document.get("resolution") else ""
        lines.append(f"- [{label}](<{document['url']}>)" + state)
    return lines + [""]


def probe(output):
    """Live access check only; never sends email or changes scanner/paper state."""
    client = SecClient()
    checks = [check_sec_filings(ticker, {}, client) for ticker in ("LCII", "LRN", "SFD")]
    endpoints = []
    # Probe the API independently: mapping-host failure does not demonstrate
    # that the separate data.sec.gov submissions host is unreachable.
    for url in (SEC_MAPPING, "https://data.sec.gov/submissions/CIK0000763744.json"):
        try:
            _, stamp = client.get_json(url)
            endpoints.append({"url": url, "status": "AVAILABLE", "retrieved_at": stamp})
        except SourceUnavailable as exc:
            endpoints.append({"url": url, "status": "UNAVAILABLE", "reason": str(exc)})
    Path(output).write_text(json.dumps({"scope": "live_source_access_probe_without_provider_statement_reconciliation",
                                      "checks": checks, "endpoints": endpoints}, indent=2) + "\n", encoding="utf-8")
    for check in checks:
        print(f"{check['ticker']}: {check['status']}; issuer identity verified: {'issuer' in check}")
    for endpoint in endpoints:
        print(f"{endpoint['url']}: {endpoint['status']}; {endpoint.get('reason', '')}")
    return all("issuer" in check and check["status"] != "UNVERIFIED" for check in checks)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Probe official SEC access without scanning or sending mail")
    parser.add_argument("--probe-output", default="sec_source_probe.json")
    args = parser.parse_args()
    raise SystemExit(0 if probe(args.probe_output) else 1)
