import json

from scan_coverage import new_coverage, record_outcome, checkpoint
from research_reporting import write_research_report


def test_partial_checkpoint_preserves_source_gaps(tmp_path):
    coverage = new_coverage(["GOOD", "UNAVAILABLE", "NOT_YET_CHECKED"])
    record_outcome(coverage, "GOOD", "candidate", "price_history")
    record_outcome(coverage, "UNAVAILABLE", "data_error", "quote", "TimeoutError")
    checkpoint(coverage, tmp_path / "research_report")
    saved = json.loads((tmp_path / "scan_coverage.json").read_text(encoding="utf-8"))
    assert saved["completed"] is False
    assert saved["processed_count"] == 2 and saved["requested_count"] == 3
    assert saved["outcomes"] == {"candidate": 1, "data_error": 1}
    assert saved["data_gaps"] == [{"ticker": "UNAVAILABLE", "stage": "quote", "outcome": "data_error", "error_type": "TimeoutError"}]
    assert not (tmp_path / "scan_coverage.tmp").exists()


def test_report_discloses_incomplete_scan(tmp_path):
    coverage = new_coverage(["ONE", "TWO"])
    record_outcome(coverage, "ONE", "quote_unavailable", "quote")
    prefix = tmp_path / "research_report"
    write_research_report([], [], prefix=str(prefix), scope={"type": "configured_universe", "stage1_coverage": coverage})
    report = prefix.with_suffix(".md").read_text(encoding="utf-8")
    assert "Stage 1 completed: False; processed 1/2" in report
    assert "recorded data gaps 1" in report
    assert "Missing data" in report


def test_stage1_accounts_for_quote_failures_and_filtered_names(monkeypatch, tmp_path):
    import fallen_angel_scanner as scanner
    monkeypatch.setattr(scanner, "get_all_tickers", lambda: ["MISSING", "FUND"])
    monkeypatch.setattr(scanner, "load_failed_tickers", lambda: {})
    monkeypatch.setattr(scanner, "save_failed_tickers", lambda value: None)
    monkeypatch.setattr(scanner, "REPORT_PREFIX", str(tmp_path / "research_report"), raising=False)
    monkeypatch.setattr(scanner, "get_stock_with_retry", lambda ticker: (None, None) if ticker == "MISSING" else (object(), {"quoteType": "ETF"}))
    monkeypatch.setattr(scanner, "currency_context", lambda info: {})
    monkeypatch.setattr(scanner, "market_cap_usd", lambda info, context: 1e9)
    candidates, _ = scanner.stage1_quick_filter()
    coverage = json.loads((tmp_path / "scan_coverage.json").read_text(encoding="utf-8"))
    assert candidates == []
    assert coverage["completed"] is True and coverage["processed_count"] == 2
    assert coverage["quote_successes"] == 1
    assert coverage["outcomes"] == {"quote_unavailable": 1, "not_equity": 1}
    assert [gap["ticker"] for gap in coverage["data_gaps"]] == ["MISSING"]
