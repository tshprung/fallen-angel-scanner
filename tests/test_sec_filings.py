from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from sec_filings import (SEC_MAPPING, SecClient, SourceUnavailable, check_sec_filings,
                         load_filing_resolutions)
from research_reporting import filing_review_summary_html, write_research_report

NOW = "2026-10-22T12:00:00Z"
CIK = 1234
SUBMISSIONS = "https://data.sec.gov/submissions/CIK0000001234.json"


def filing(form="10-Q", filed="2026-08-11", period="2026-06-30", items="", seq=1):
    return {"form": form, "filingDate": filed, "reportDate": period, "items": items,
            "accessionNumber": f"0000001234-26-{seq:06d}", "primaryDocument": f"report{seq}.htm",
            "acceptanceDateTime": filed + "T16:00:00Z"}


def block(rows):
    return {key: [row[key] for row in rows] for key in filing()}


def evidence(period="2026-06-30"):
    return {name: {"asof": period} for name in ("balance", "cashflow", "income")}


def client(rows=None, extra=None):
    payload = {"cik": CIK, "tickers": ["AAA"], "name": "Example Issuer", "filings": {
        "recent": block(rows or [filing()]), "files": []}}
    data = {SEC_MAPPING: {"fields": ["cik", "name", "ticker", "exchange"],
                         "data": [[CIK, "Example Issuer", "AAA", "NYSE"]]}, SUBMISSIONS: payload}
    data.update(extra or {})
    return SimpleNamespace(get_json=lambda url: (deepcopy(data[url]), NOW)), data


def check(rows=None, data=None, resolutions=None):
    fixture, _ = client(rows)
    return check_sec_filings("AAA", data or evidence(), fixture, NOW, resolutions)


def test_metadata_check_keeps_verified_issuer_dates_and_actual_filing_url():
    result = check()
    assert result["status"] == "METADATA_CHECKED"
    assert not result["blocks_selection"]
    assert result["cik"] == "0000001234"
    assert result["latest_financial_report"]["url"] == "https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/report1.htm"
    assert "not automatically verified" in result["notice"]


@pytest.mark.parametrize("name", ["balance", "cashflow", "income"])
def test_each_provider_statement_must_cover_the_newest_official_period(name):
    data = evidence("2026-09-30")
    data[name]["asof"] = "2026-06-30"
    result = check([filing(filed="2026-10-21", period="2026-09-30")], data)
    assert result["status"] == "REVIEW_REQUIRED"
    assert name in result["findings"][0]


def test_results_release_after_latest_periodic_report_catches_unreconciled_earnings_or_warning():
    result = check([filing(), filing("8-K", "2026-10-20", "2026-10-20", "2.02,9.01", 2)])
    assert result["blocks_selection"]
    assert "Results/outlook" in result["findings"][0]
    # Once the periodic report is published and all statement periods cover it,
    # the older results metadata no longer supplies this particular freshness flag.
    result = check([filing(filed="2026-10-21", period="2026-09-30"),
                    filing("8-K", "2026-10-20", "2026-10-20", "2.02,9.01", 2)], evidence("2026-09-30"))
    assert result["status"] == "METADATA_CHECKED"


@pytest.mark.parametrize("item", ["1.01", "1.03", "2.03", "2.04", "3.01", "3.02", "4.02"])
def test_material_event_items_block_ordinary_selection(item):
    assert check([filing(), filing("8-K", "2026-10-13", "2026-10-09", item, 2)])["blocks_selection"]


def test_merger_filing_older_than_news_window_is_still_flagged():
    result = check([filing(), filing("425", "2026-06-30", "2026-06-30", seq=2)])
    assert result["event_filings"][0]["form"] == "425"
    assert result["blocks_selection"]


def test_current_report_without_item_metadata_is_unknown_not_clear():
    assert "unavailable" in check([filing(), filing("8-K", "2026-10-13", items="", seq=2)])["findings"][0]


def test_accession_review_does_not_clear_an_amendment_or_stale_statements():
    rows = [filing(), filing("425", "2026-10-13", seq=2)]
    first = check(rows)
    document = first["event_filings"][0]
    key = "0000001234:" + document["accessionNumber"]
    reviews = {key: {"source_url": document["url"], "reviewed_at": "2026-10-21",
                     "finding": "Fixture only: transaction terminated; issuer confirmed no ongoing deal"}}
    assert check(rows, resolutions=reviews)["status"] == "METADATA_CHECKED"
    rows.append(filing("S-4/A", "2026-10-21", seq=3))
    assert check(rows, resolutions=reviews)["blocks_selection"]
    assert check(rows[:2], evidence("2026-03-31"), reviews)["blocks_selection"]
    reviews[key]["source_url"] = "https://example.com/other-document"
    assert check(rows[:2], resolutions=reviews)["blocks_selection"]


def test_future_filings_and_acceptance_times_cannot_be_used_as_known_events():
    result = check([filing(), filing("425", "2026-10-23", seq=2),
                    filing("425", "2026-10-22", seq=3)])  # accepted 16:00, after 12:00 check
    assert result["status"] == "METADATA_CHECKED"


def test_mismatched_issuer_and_misaligned_arrays_fail_closed():
    fixture, data = client()
    data[SUBMISSIONS]["tickers"] = ["OTHER"]
    assert check_sec_filings("AAA", evidence(), fixture, NOW)["status"] == "UNVERIFIED"
    data[SUBMISSIONS]["tickers"] = ["AAA"]
    data[SUBMISSIONS]["filings"]["recent"]["reportDate"] = []
    assert check_sec_filings("AAA", evidence(), fixture, NOW)["blocks_selection"]


def test_archive_history_is_read_when_recent_arrays_do_not_cover_the_window():
    fixture, data = client()
    name = "CIK0000001234-submissions-001.json"
    data[SUBMISSIONS]["filings"]["files"] = [{"name": name, "filingFrom": "2026-01-01", "filingTo": "2026-07-01"}]
    data["https://data.sec.gov/submissions/" + name] = block([filing("425", "2026-06-30", seq=2)])
    assert check_sec_filings("AAA", evidence(), fixture, NOW)["blocks_selection"]


def test_local_listings_are_not_reported_as_sec_verified_or_queried():
    fixture = SimpleNamespace(get_json=Mock(side_effect=AssertionError("Must use local regulator")))
    result = check_sec_filings("AAA.L", evidence(), fixture, NOW)
    assert result["status"] == "NOT_COVERED"
    fixture.get_json.assert_not_called()


def test_blocked_source_and_stale_cache_cannot_produce_clearance(tmp_path, monkeypatch):
    monkeypatch.setattr("sec_filings.time.sleep", lambda _: None)
    response = SimpleNamespace(status_code=200, json=lambda: {"fields": [], "data": []})
    session = SimpleNamespace(get=Mock(return_value=response))
    first = SecClient(tmp_path, session, NOW)
    first.get_json(SEC_MAPPING)
    session.get.reset_mock()
    SecClient(tmp_path, session, NOW).get_json(SEC_MAPPING)
    session.get.assert_not_called()
    session.get.return_value = SimpleNamespace(status_code=403)
    stale = SecClient(tmp_path, session, "2026-11-01T12:00:00Z")
    for _ in range(2):
        with pytest.raises(SourceUnavailable, match="403"):
            stale.get_json(SEC_MAPPING)
    assert session.get.call_count == 1  # repeat failures are cached in memory, not retried per ticker
    result = check_sec_filings("AAA", evidence(), stale, "2026-11-01T12:00:00Z")
    assert result["status"] == "UNVERIFIED" and result["blocks_selection"]


def test_reports_and_email_preserve_held_names_and_sources(tmp_path):
    result = check([filing(), filing("425", "2026-10-13", seq=2)])
    audit = [{"ticker": "AAA", "decision": "filing_review", "reason": "; ".join(result["findings"]),
              "official_filing_check": result}]
    write_research_report(audit, [], str(tmp_path / "report"))
    saved = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert saved["selected_tickers"] == []
    for path in (tmp_path / "report.md", tmp_path / "filing_review.md"):
        assert result["event_filings"][0]["url"] in path.read_text(encoding="utf-8")
    audit[0]["reason"] = "<script>external text</script>"
    html = filing_review_summary_html(audit)
    assert "<script>" not in html
    assert "did not qualify" in html and result["event_filings"][0]["url"] in html


def test_review_registry_rejects_blanket_or_undocumented_clearance(tmp_path):
    path = tmp_path / "reviews.json"
    path.write_text(json.dumps({"AAA": {"finding": "safe"}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_filing_resolutions(path)


def test_network_diagnostics_do_not_print_exception_headers_or_contact(tmp_path, monkeypatch):
    monkeypatch.setattr("sec_filings.time.sleep", lambda _: None)
    session = SimpleNamespace(get=Mock(side_effect=requests.exceptions.SSLError("sensitive-header@example.com")))
    result = check_sec_filings("AAA", evidence(), SecClient(tmp_path, session, NOW), NOW)
    assert result["status"] == "UNVERIFIED"
    assert result["findings"] == ["SEC network request failed (SSLError)"]
    assert "sensitive" not in json.dumps(result)
    assert session.get.call_count == 1


def test_all_held_run_still_sends_a_review_report_without_paper_selections(monkeypatch, tmp_path):
    import scanner_entry
    scanner = scanner_entry.scanner
    monkeypatch.setattr(scanner, "load_memory", lambda: {"sent_stocks": {}, "tracked_prices": {}})
    monkeypatch.setattr(scanner, "check_price_alerts", lambda _: [])
    monkeypatch.setattr(scanner, "stage1_quick_filter", lambda: ([{"ticker": "LCII"}], []))
    monkeypatch.setattr(scanner, "REPORT_PREFIX", str(tmp_path / "research_report"), raising=False)
    send = Mock(return_value=False)
    monkeypatch.setattr(scanner, "send_email", send)
    scanner.main()
    subject, html = send.call_args.args
    assert "0 research candidates" in subject and "1 filing review holds" in subject
    assert "Held for filing review" in html and "LCII" in html
    assert not (tmp_path / "paper_tracking.json").exists()
