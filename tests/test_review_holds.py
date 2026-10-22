import json

import pytest

from filing_review import write_filing_queue
from review_holds import load_review_holds


def test_sourced_holds_block_production_selection_before_provider_or_dedup(monkeypatch, tmp_path):
    import scanner_entry
    scanner = scanner_entry.scanner

    def unexpected(*args, **kwargs):
        raise AssertionError("Held candidates must not request provider data or pass through dedup")

    monkeypatch.setattr(scanner, "get_stock_with_retry", unexpected)
    monkeypatch.setattr(scanner, "should_send_stock", unexpected)
    tickers = ["LCII", "LRN", "SFD"]
    assert scanner.stage2_deep_analysis([{"ticker": ticker} for ticker in tickers], {}) == ([], [])
    audit = scanner._last_research_audit
    assert [item["ticker"] for item in audit] == tickers
    assert all(item["decision"] == "event_review" for item in audit)
    assert all("valuation" not in item for item in audit)
    path = tmp_path / "queue.md"
    write_filing_queue(audit, path)
    output = path.read_text(encoding="utf-8")
    for item in audit:
        assert item["review_hold"]["release_condition"] in output
        assert item["review_hold"]["sources"][0]["url"] in output
        for note in item["review_hold"].get("review_notes", []):
            assert note["finding"] in output
            assert note["source_url"] in output


def test_dated_research_notes_do_not_clear_a_hold_and_require_matching_sources(tmp_path):
    records = load_review_holds()
    assert records["SFD"]["review_notes"] and records["SFD"]["status"] == "PENDING"
    records["SFD"]["review_notes"][0]["source_url"] = "https://example.com/unreviewed"
    path = tmp_path / "holds.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    with pytest.raises(ValueError, match="matching dated source"):
        load_review_holds(path)


def test_holds_do_not_expire_or_clear_without_recorded_resolution(tmp_path):
    records = load_review_holds()
    records["LCII"]["reviewed_at"] = "2020-01-01"
    path = tmp_path / "holds.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    assert "LCII" in load_review_holds(path)
    assert "OTHER" not in load_review_holds(path)
    records["LCII"]["status"] = "RESOLVED"
    path.write_text(json.dumps(records), encoding="utf-8")
    with pytest.raises(ValueError, match="Resolution evidence"):
        load_review_holds(path)
    records["LCII"]["resolution"] = "Fixture: documented resolution, not an actual issuer finding"
    path.write_text(json.dumps(records), encoding="utf-8")
    assert "LCII" not in load_review_holds(path)


def test_risk_footer_describes_production_threshold_and_no_probability():
    from scanner_enhanced import _trend_section
    html = _trend_section([{"ticker": "AAA", "risk_score_raw": 1, "risk_score": 1}])
    assert "risk ≥4 is excluded" in html
    assert "not a bankruptcy" in html
    assert "4/10 candidate is admitted" not in html
