from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from disclosure_watch import (ASBIS_REPORTS, asbis_documents, collect_updates,
                              fetch_asbis, has_updates, load_watchlist, run_watch, summary_html)
from sec_filings import SourceUnavailable

NOW = "2026-10-22T12:00:00Z"


def watch(source="SEC", ticker="PNR"):
    return {"ticker": ticker, "source": source, "expected_report_date": "2026-10-27",
            "expected_period_end": "2026-09-30", "question": "Review funding and recovery evidence"}


def checked(period="2026-06-30", accession="old"):
    return {"status": "REVIEW_REQUIRED", "cik": "0000077360", "issuer": "Pentair",
            "checked_at": NOW, "blocks_selection": True,
            "latest_financial_report": {"accessionNumber": accession, "form": "10-Q",
                "filingDate": "2026-07-28", "reportDate": period,
                "url": "https://www.sec.gov/Archives/edgar/data/77360/report.htm"}, "event_filings": []}


def test_initial_metadata_is_a_baseline_and_unchanged_metadata_is_quiet():
    metadata = checked()
    original = deepcopy(metadata)
    report, state = collect_updates([watch()], now=NOW, checker=lambda *a, **k: metadata)
    assert report["watches"][0]["status"] == "AWAITING_EXPECTED_REPORT"
    assert not has_updates(report)
    again, state2 = collect_updates([watch()], state, now=NOW, checker=lambda *a, **k: metadata)
    assert not has_updates(again) and state2 == state
    assert metadata == original and metadata["blocks_selection"]


def test_new_periodic_filing_requires_review_and_does_not_repeat_on_each_run():
    _, state = collect_updates([watch()], now=NOW, checker=lambda *a, **k: checked())
    report, state2 = collect_updates([watch()], state, now="2026-10-28T12:00:00Z",
                                    checker=lambda *a, **k: checked("2026-09-30", "new"))
    row = report["watches"][0]
    assert row["status"] == "EXPECTED_REPORT_REQUIRES_REVIEW" and has_updates(report)
    assert [doc["id"] for doc in row["new_documents"]] == ["new"]
    again, _ = collect_updates([watch()], state2, now="2026-10-28T13:00:00Z",
                               checker=lambda *a, **k: checked("2026-09-30", "new"))
    assert not has_updates(again)


def test_first_check_after_target_report_is_published_is_not_silently_baselined():
    report, _ = collect_updates([watch()], now="2026-10-28T12:00:00Z",
                                checker=lambda *a, **k: checked("2026-09-30", "new"))
    assert has_updates(report)


def test_new_results_current_report_is_detected_before_a_new_periodic_filing():
    _, state = collect_updates([watch()], now=NOW, checker=lambda *a, **k: checked())
    metadata = checked()
    metadata["event_filings"] = [dict(metadata["latest_financial_report"], form="8-K",
                                       accessionNumber="results", filingDate="2026-10-27")]
    report, _ = collect_updates([watch()], state, now="2026-10-27T15:00:00Z",
                                checker=lambda *a, **k: metadata)
    assert report["watches"][0]["status"] == "NEW_SOURCE_DOCUMENTS" and has_updates(report)
    assert not report["watches"][0]["expected_report_listed"]


def test_source_failure_retains_comparison_history_without_reusing_it_as_clearance():
    _, state = collect_updates([watch()], now=NOW, checker=lambda *a, **k: checked())
    original = deepcopy(state)
    report, next_state = collect_updates([watch()], state, now=NOW,
        checker=lambda *a, **k: {"status": "UNVERIFIED", "findings": ["SEC HTTP 403"]})
    row = report["watches"][0]
    assert row["status"] == "UNVERIFIED" and row["documents"] == []
    assert "expected_report_listed" not in row and not has_updates(report)
    assert state == original == next_state


def test_unconfirmed_report_after_checkpoint_is_a_source_question_not_a_financial_failure():
    report, state = collect_updates([watch()], now="2026-10-28T12:00:00Z",
                                    checker=lambda *a, **k: checked())
    assert report["watches"][0]["status"] == "EXPECTED_REPORT_NOT_CONFIRMED"
    assert has_updates(report) and "solvency" not in report["watches"][0]
    again, _ = collect_updates([watch()], state, now="2026-10-29T12:00:00Z",
                               checker=lambda *a, **k: checked())
    assert not has_updates(again)


def test_asbis_matches_period_in_table_context_and_rejects_unrelated_or_external_links():
    body = '''<html><table><tr><td>2026 Q3</td><td>
      <a href="/download/q3.pdf">Consolidated interim financial statements</a>
      <a href="https://evil.example/q3.pdf">External copy</a>
      <a href="/download/q3.pdf?redirect=elsewhere">Redirect</a>
      <a href="/news/q3.html">News</a></td></tr>
      <tr><td>2026 H1</td><td><a href="/download/h1.pdf">H1 statements</a></td></tr></table></html>'''
    docs = asbis_documents(body, "2026-09-30")
    assert [doc["url"] for doc in docs] == ["https://investor.asbis.com/download/q3.pdf"]
    report, _ = collect_updates([watch("ASBIS", "ASB.WA")], now=NOW, asbis_fetch=lambda p: docs)
    assert report["watches"][0]["status"] == "EXPECTED_REPORT_LINKS_REQUIRE_REVIEW"
    assert has_updates(report) and "METADATA_CHECKED" not in str(report)


def test_asbis_access_denial_and_oversize_are_unverified_and_responses_close():
    for status, chunks in [(403, []), (200, [b"x" * (2 * 1024 * 1024 + 1)]), (200, [b"Login required"])]:
        response = SimpleNamespace(status_code=status, iter_content=lambda n: iter(chunks), close=Mock())
        session = SimpleNamespace(get=Mock(return_value=response))
        with pytest.raises(SourceUnavailable):
            fetch_asbis("2026-09-30", session)
        response.close.assert_called_once()
        assert session.get.call_args.kwargs["allow_redirects"] is False


def test_malformed_comparison_state_does_not_prevent_a_fresh_source_check():
    report, _ = collect_updates([watch()], {"PNR": "bad state"}, now=NOW,
                                checker=lambda *a, **k: checked("2026-09-30", "new"))
    assert has_updates(report)


def test_html_escapes_source_labels_and_never_links_script_urls():
    report, _ = collect_updates([watch()], now=NOW, checker=lambda *a, **k: checked())
    row = report["watches"][0]
    row["question"] = '<img src=x onerror="bad()">'
    row["documents"] = [{"url": "javascript:alert(1)", "label": "unsafe"}]
    output = summary_html(report)
    assert "<img" not in output and "&lt;img" in output and "javascript:" not in output


def test_default_watchlist_has_no_invented_lzb_date_and_rejects_invalid_records(tmp_path):
    watches = load_watchlist()
    assert next(row for row in watches if row["ticker"] == "LZB")["expected_report_date"] is None
    path = tmp_path / "watch.json"
    path.write_text(json.dumps({"watches": [watch(), watch()]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_watchlist(path)


def test_cli_writes_only_followup_artifacts_without_importing_scanner_state(tmp_path, monkeypatch):
    monkeypatch.setattr("disclosure_watch.collect_updates", lambda *a, **k:
                        collect_updates([watch()], now=NOW, checker=lambda *a, **k: checked()))
    run_watch(tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {
        "disclosure_watch.json", "disclosure_watch.md", "disclosure_watch_state.json"}


def test_disclosure_only_update_can_generate_report_without_stock_candidates(monkeypatch, tmp_path):
    import scanner_entry
    scanner = scanner_entry.scanner
    watch_report, _ = collect_updates([watch()], now="2026-10-28T12:00:00Z",
                                      checker=lambda *a, **k: checked("2026-09-30", "new"))
    monkeypatch.setattr(scanner, "_last_disclosure_watch", watch_report, raising=False)
    monkeypatch.setattr(scanner, "REPORT_SCOPE", {"type": "subset"}, raising=False)
    monkeypatch.setattr(scanner, "REPORT_PREFIX", str(tmp_path / "research_report"), raising=False)
    monkeypatch.setattr(scanner, "load_memory", lambda: {})
    monkeypatch.setattr(scanner, "save_memory", Mock())
    monkeypatch.setattr(scanner, "check_price_alerts", lambda memory: [])
    monkeypatch.setattr(scanner, "stage1_quick_filter", lambda: ([], []))
    send = Mock(return_value=False)
    monkeypatch.setattr(scanner, "send_email", send)
    monkeypatch.setattr(scanner, "enrich_research_audit", Mock())
    scanner.main()
    send.assert_called_once()
    assert "disclosure updates" in send.call_args.args[0]
    assert "Disclosure follow-up" in send.call_args.args[1]
    assert "EXPECTED_REPORT_REQUIRES_REVIEW" in send.call_args.args[1]
    report = json.loads((tmp_path / "research_report.json").read_text(encoding="utf-8"))
    assert report["selected_tickers"] == [] and report["candidates"] == []
