import json
from unittest.mock import Mock

import pytest

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


def test_document_enrichment_crash_preserves_financial_audit_and_does_not_send(monkeypatch, tmp_path):
    import fallen_angel_scanner as scanner
    audit = [{"ticker": "AAA", "decision": "not_selected", "reason": "Completed financial decision"}]
    monkeypatch.setattr(scanner, "load_memory", lambda: {})
    monkeypatch.setattr(scanner, "check_price_alerts", lambda memory: [])
    monkeypatch.setattr(scanner, "stage1_quick_filter", lambda: ([{"ticker": "AAA"}], []))
    def analyze(*args):
        monkeypatch.setattr(scanner, "_last_research_audit", audit)
        return [], []
    monkeypatch.setattr(scanner, "stage2_deep_analysis", analyze)
    monkeypatch.setattr(scanner, "enrich_research_audit", Mock(side_effect=RuntimeError("fixture parser failure")))
    monkeypatch.setattr(scanner, "REPORT_PREFIX", str(tmp_path / "research_report"), raising=False)
    monkeypatch.setattr(scanner, "REPORT_SCOPE", {"type": "fixture"}, raising=False)
    send = Mock()
    monkeypatch.setattr(scanner, "send_email", send)
    with pytest.raises(RuntimeError, match="parser failure"):
        scanner.main()
    saved = json.loads((tmp_path / "research_report.json").read_text(encoding="utf-8"))
    assert saved["candidates"] == audit
    assert saved["scan_scope"]["filing_content_collection"] == "PENDING"
    assert "PENDING" in (tmp_path / "research_report.md").read_text(encoding="utf-8")
    send.assert_not_called()
    assert not (tmp_path / "paper_tracking.json").exists()


def test_quotes_are_fetched_once_per_run_and_never_reused_across_runs(monkeypatch):
    from types import SimpleNamespace
    import fallen_angel_scanner as scanner
    ticker_factory = Mock(side_effect=lambda ticker: SimpleNamespace(info={"currency": "USD", "marketCap": 1e9}))
    monkeypatch.setattr(scanner.yf, "Ticker", ticker_factory)
    def run():
        first, info = scanner.get_stock_with_retry("AAA")
        info["currency"] = "EUR"  # A caller cannot corrupt the cached quote snapshot.
        second, cached = scanner.get_stock_with_retry("AAA")
        assert first is second and cached["currency"] == "USD"
        assert cached["_scanner_quote_observed_at"]
    monkeypatch.setattr(scanner, "_run_main", run)
    scanner.main()
    assert scanner._run_quote_cache is None and ticker_factory.call_count == 1
    scanner.main()
    assert scanner._run_quote_cache is None and ticker_factory.call_count == 2


def test_partial_yahoo_quote_without_currency_is_not_accepted(monkeypatch):
    from types import SimpleNamespace
    import fallen_angel_scanner as scanner
    from scanner_currency import CurrencyUnavailable
    monkeypatch.setattr(scanner, "_run_quote_cache", {})
    monkeypatch.setattr(scanner.yf, "Ticker", lambda ticker: SimpleNamespace(info={"trailingPegRatio": None}))
    with pytest.raises(CurrencyUnavailable, match="verified currency"):
        scanner.get_stock_with_retry("AAA")
    assert scanner._run_quote_cache == {}


def test_systemic_company_source_failure_preserves_report_and_fails_before_mail(monkeypatch, tmp_path):
    import fallen_angel_scanner as scanner
    audit = [{"ticker": f"TEST{i}", "decision": "analysis_error" if i < 8 else "not_selected",
              "reason": "Fixture incomplete provider response"} for i in range(12)]
    monkeypatch.setattr(scanner, "load_memory", lambda: {})
    monkeypatch.setattr(scanner, "check_price_alerts", lambda memory: [])
    monkeypatch.setattr(scanner, "stage1_quick_filter", lambda: ([{"ticker": "TEST"}], []))
    def analyze(*args):
        monkeypatch.setattr(scanner, "_last_research_audit", audit)
        return [], []
    monkeypatch.setattr(scanner, "stage2_deep_analysis", analyze)
    monkeypatch.setattr(scanner, "REPORT_PREFIX", str(tmp_path / "research_report"), raising=False)
    monkeypatch.setattr(scanner, "REPORT_SCOPE", {"type": "fixture"}, raising=False)
    send, enrich = Mock(), Mock()
    monkeypatch.setattr(scanner, "send_email", send)
    monkeypatch.setattr(scanner, "enrich_research_audit", enrich)
    with pytest.raises(RuntimeError, match="Systemic company-analysis"):
        scanner.main()
    saved = json.loads((tmp_path / "research_report.json").read_text(encoding="utf-8"))
    assert saved["candidates"] == audit
    assert saved["scan_scope"]["provider_health"]["company_analysis_errors"] == 8
    assert saved["scan_scope"]["provider_health"]["systemic_failure"] is True
    assert saved["scan_scope"]["filing_content_collection"] == "SKIPPED_SOURCE_FAILURE"
    assert scanner._run_quote_cache is None
    send.assert_not_called()
    enrich.assert_not_called()


def test_source_health_does_not_label_price_outage_as_no_matches():
    from scan_coverage import provider_health
    coverage = new_coverage([f"TEST{i}" for i in range(12)])
    for ticker in coverage["requested_symbols"]:
        record_outcome(coverage, ticker, "quote_unavailable", "quote")
    assert provider_health(coverage)["systemic_failure"] is True
    assert provider_health(audit=[{"decision": "analysis_error"}, {"decision": "unverified"}])["status"] == "DEGRADED"
    assert not provider_health(audit=[{"decision": "analysis_error"}, {"decision": "unverified"}])["systemic_failure"]
