"""Independent disclosure follow-up; never changes admission, holds or paper state."""

from datetime import date
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

from lxml import html, etree
import requests

from filing_review import safe_website
from sec_filings import SecClient, SourceUnavailable, check_sec_filings, utc

WATCHLIST = Path(__file__).with_name("disclosure_watchlist.json")
ASBIS_REPORTS = "https://investor.asbis.com/financial-reports"
NOTICE = ("Disclosure follow-up only. New links or filing metadata require review; "
          "they do not verify financial contents, resolve a hold, or select a stock. "
          "Missing access is unverified, not evidence that an issuer failed to report.")


def load_watchlist(path=WATCHLIST):
    watches = json.loads(Path(path).read_text(encoding="utf-8"))["watches"]
    if not isinstance(watches, list) or len(watches) > 10:
        raise ValueError("Disclosure watchlist must have at most ten records")
    seen = set()
    for row in watches:
        if not isinstance(row, dict):
            raise ValueError("Invalid disclosure watch record")
        ticker = row.get("ticker")
        if (not isinstance(ticker, str) or not re.fullmatch(r"[A-Z0-9.-]{1,20}", ticker)
                or ticker in seen or row.get("source") not in {"SEC", "ASBIS"}
                or not isinstance(row.get("question"), str) or not row["question"].strip()):
            raise ValueError("Invalid disclosure watch record")
        seen.add(ticker)
        for key in ("expected_report_date", "expected_period_end"):
            if row.get(key) is not None:
                date.fromisoformat(row[key])
        if row["source"] == "ASBIS" and ticker != "ASB.WA":
            raise ValueError("ASBIS source is only valid for ASB.WA")
        if row.get("expected_period_end") and not row.get("expected_report_date"):
            raise ValueError("An expected financial period needs a dated report checkpoint")
        if row.get("expected_period_end") and row["expected_period_end"] > row["expected_report_date"]:
            raise ValueError("Expected report date precedes its financial period")
    return watches


def asbis_documents(body, period):
    """Find target-period issuer report links; do not download/interpret reports."""
    if not period:
        raise SourceUnavailable("ASBIS target period is not configured")
    target = date.fromisoformat(period)
    quarter = (target.month - 1) // 3 + 1
    year = target.year
    patterns = [rf"\b{year}\s*Q{quarter}\b", rf"\bQ{quarter}\s*{year}\b"]
    if target.month == 9:
        patterns += [rf"nine months.{{0,60}}{year}", rf"30\s+September\s+{year}"]
    tree = html.fromstring(body)
    documents = {}
    for anchor in tree.xpath("//a[@href]"):
        rows = anchor.xpath("ancestor::tr[1]")
        context = " ".join((rows[0] if rows else anchor).text_content().split())
        if not any(re.search(pattern, context, re.I) for pattern in patterns):
            continue
        url = urljoin(ASBIS_REPORTS, anchor.get("href"))
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc != "investor.asbis.com"
                or not parts.path.startswith("/download/") or parts.query or parts.fragment
                or not parts.path.lower().endswith((".pdf", ".html", ".xhtml"))):
            continue
        label = " ".join(anchor.text_content().split()) or "Issuer financial report"
        documents[url] = {"id": url, "url": url, "label": label[:250], "period": period}
    return list(documents.values())


def fetch_asbis(period, session=None):
    response = None
    try:
        response = (session or requests).get(ASBIS_REPORTS, timeout=(5, 20),
                                            allow_redirects=False, stream=True)
        if response.status_code != 200:
            raise SourceUnavailable(f"ASBIS report index HTTP {response.status_code}")
        content = bytearray()
        for chunk in response.iter_content(65536):
            content.extend(chunk)
            if len(content) > 2 * 1024 * 1024:
                raise SourceUnavailable("ASBIS report index exceeds size limit")
        if not content:
            raise SourceUnavailable("ASBIS report index is empty")
        tree = html.fromstring(bytes(content))
        text = " ".join(tree.text_content().split())
        if "ASBIS" not in text.upper() or "financial reports" not in text.lower():
            raise SourceUnavailable("ASBIS report index identity/content not confirmed")
        return asbis_documents(bytes(content), period)
    except (requests.RequestException, ValueError, etree.ParserError, etree.XMLSyntaxError) as exc:
        raise SourceUnavailable(f"ASBIS report index unavailable ({type(exc).__name__})") from exc
    finally:
        if response is not None:
            response.close()


def collect_updates(watches, previous=None, now=None, sec_client=None,
                    checker=check_sec_filings, asbis_fetch=fetch_asbis):
    stamp = utc(now)
    previous = previous or {}
    state, records = {}, []
    client = sec_client or SecClient(now=now)
    for watch in watches:
        ticker = watch["ticker"]
        old = previous.get(ticker)
        if not (isinstance(old, dict) and isinstance(old.get("document_ids"), list)
                and all(isinstance(value, str) for value in old["document_ids"])):
            old = None
        row = dict(watch, checked_at=stamp.isoformat(), documents=[], new_documents=[], actionable_change=False)
        records.append(row)
        try:
            latest = None
            if watch["source"] == "SEC":
                check = checker(ticker, {}, client=client, now=stamp)
                if check.get("status") not in {"METADATA_CHECKED", "REVIEW_REQUIRED"}:
                    raise SourceUnavailable("SEC issuer/filing metadata unavailable")
                latest = check.get("latest_financial_report")
                if not latest or not check.get("cik") or not check.get("issuer"):
                    raise SourceUnavailable("SEC issuer/period identity unavailable")
                documents = [{"id": doc["accessionNumber"], "url": doc["url"],
                              "label": f"{doc['form']} filed {doc['filingDate']}",
                              "period": doc.get("reportDate"), "filed_at": doc["filingDate"]}
                             for doc in [latest] + check.get("event_filings", [])]
                row["latest_financial_period"] = latest["reportDate"]
                row["issuer"] = check["issuer"]
                row["source_checked_at"] = check.get("checked_at")
            else:
                documents = asbis_fetch(watch.get("expected_period_end"))
                row["source_index"] = ASBIS_REPORTS
            documents = list({doc["id"]: doc for doc in documents}.values())
            ids = sorted(doc["id"] for doc in documents)
            old_ids = set((old or {}).get("document_ids", []))
            new = [doc for doc in documents if doc["id"] not in old_ids] if old is not None else []
            target = watch.get("expected_period_end")
            available = bool(target and (latest and latest["reportDate"] >= target
                                         or watch["source"] == "ASBIS" and documents))
            due = watch.get("expected_report_date")
            expected_status = ("EXPECTED_REPORT_LINKS_REQUIRE_REVIEW" if watch["source"] == "ASBIS"
                               else "EXPECTED_REPORT_REQUIRES_REVIEW")
            status = (expected_status if available else "NEW_SOURCE_DOCUMENTS" if new
                      else "EXPECTED_REPORT_NOT_CONFIRMED" if due and stamp.date() > date.fromisoformat(due)
                      else "AWAITING_EXPECTED_REPORT" if due else "BASELINE_RECORDED" if old is None
                      else "UNCHANGED")
            row.update(status=status, source_status="AVAILABLE", expected_report_listed=available,
                       documents=documents[:20], new_documents=new[:20],
                       omitted_document_count=max(0, len(documents) - 20),
                       actionable_change=bool(new) or bool(available and old is None)
                       or bool(status == "EXPECTED_REPORT_NOT_CONFIRMED" and (old or {}).get("status") != status))
            state[ticker] = {"document_ids": ids, "observed_at": stamp.isoformat(), "status": status}
        except (SourceUnavailable, ValueError, KeyError, TypeError) as exc:
            row.update(status="UNVERIFIED", source_status="UNAVAILABLE",
                       reason=str(exc) if isinstance(exc, SourceUnavailable) else "Malformed disclosure metadata")
            # Retain only comparison history. It is never used as current clearance.
            if old is not None:
                state[ticker] = old
    return {"checked_at": stamp.isoformat(), "notice": NOTICE, "watches": records}, state


def has_updates(report):
    return any(row.get("actionable_change") for row in (report or {}).get("watches", []))


def summary_html(report):
    if not report:
        return ""
    lines = ["<h2>Disclosure follow-up</h2><p>" + escape(NOTICE) + "</p>"]
    for row in report["watches"]:
        lines.append(f"<p><strong>{escape(row['ticker'])}</strong>: {escape(row['status'])}. "
                     f"Checked {escape(row['checked_at'])}. {escape(row['question'])}</p>")
        if row.get("reason"):
            lines.append("<p>" + escape(row["reason"]) + "</p>")
        for doc in row.get("new_documents", []) or (row.get("documents", [])[:1]):
            url = safe_website(doc["url"])
            if url:
                lines.append(f'<p><a href="{escape(url, quote=True)}">{escape(doc["label"])}</a></p>')
    return "".join(lines)


def run_watch(output_dir=".", watchlist=WATCHLIST, now=None):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "disclosure_watch_state.json"
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, ValueError):
        previous = {}
    report, state = collect_updates(load_watchlist(watchlist), previous, now)
    for name, data in (("disclosure_watch.json", report), ("disclosure_watch_state.json", state)):
        (directory / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Disclosure follow-up", "", NOTICE, "", f"Checked: {report['checked_at']}", ""]
    for row in report["watches"]:
        lines += [f"## {row['ticker']}: {row['status']}", "", row["question"], ""]
        if row.get("reason"):
            lines += [row["reason"], ""]
        for doc in row["documents"]:
            lines.append(f"- [{escape(doc['label'])}](<{doc['url']}>)")
    (directory / "disclosure_watch.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=NOTICE)
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args()
    result = run_watch(args.output_dir)
    for row in result["watches"]:
        print(f"{row['ticker']}: {row['status']}")
