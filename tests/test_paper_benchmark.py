import json

import pandas as pd
import pytest

from paper_tracking import benchmark_observation, refresh, record_selections, PERFORMANCE_VERSION


def observed(currency="USD"):
    return {"quote_currency": currency, "performance": {"status": "tracking", "method_version": PERFORMANCE_VERSION,
        "entry_session": "2026-10-22", "mark_session": "2026-10-23", "return_local_pct": 50}}


def prices():
    return pd.DataFrame({"Open": [100., 105.], "Close": [105., 110.]}, index=pd.to_datetime(["2026-10-22", "2026-10-23"]))


def test_benchmark_is_same_date_open_to_close_and_difference_is_percentage_points():
    result = benchmark_observation(observed(), prices())
    assert result["status"] == "MATCHED"
    assert result["return_pct"] == pytest.approx(10)
    assert result["stock_minus_benchmark_pp"] == pytest.approx(40)
    assert benchmark_observation(observed("GBP"), prices())["status"] == "UNSUPPORTED_CURRENCY"


@pytest.mark.parametrize("problem", ["missing_entry", "missing_exit", "duplicate", "bad_close", "bounds"])
def test_bad_benchmark_data_does_not_shift_dates_or_claim_outperformance(problem):
    frame = prices()
    if problem == "missing_entry": frame = frame.iloc[1:]
    if problem == "missing_exit": frame = frame.iloc[:1]
    if problem == "duplicate": frame = pd.concat([frame, frame.iloc[:1]])
    if problem == "bad_close": frame.iloc[0, frame.columns.get_loc("Close")] = float("nan")
    if problem == "bounds": frame["High"], frame["Low"] = 90., 80.
    result = benchmark_observation(observed(), frame)
    assert result["status"] == "UNVERIFIED" and "return_pct" not in result


def test_benchmark_failure_preserves_stock_performance_and_fetches_only_once(tmp_path):
    path = tmp_path/"paper.json"
    for symbol in ("AAA", "BBB"):
        record_selections([{"ticker": symbol,"currency": "USD","current_price": 100}], path, now="2026-10-21T18:30Z")
    calls = []
    def loader(symbol, start):
        calls.append(symbol)
        if symbol == "SPY": raise RuntimeError("unavailable")
        return prices()
    data = refresh(path, loader, now="2026-10-24T12:00Z")
    assert calls.count("SPY") == 1
    for row in data["selections"]:
        assert row["performance"]["return_local_pct"] == pytest.approx(10)
        assert row["performance"]["benchmark"]["status"] == "UNVERIFIED"


def test_benchmark_refreshes_for_frozen_completed_stock_without_rewriting_selection(tmp_path):
    path = tmp_path/"paper.json"
    original = record_selections([{"ticker":"AAA","currency":"USD","current_price":100}],path,now="2026-10-21T18:30Z")
    row = original["selections"][0]
    row["performance"] = {**observed()["performance"],"status":"complete_12m"}
    path.write_text(json.dumps(original),encoding="utf-8")
    calls=[]
    def loader(symbol,start):
        calls.append(symbol)
        return prices()
    updated=refresh(path,loader,now="2027-11-01T12:00Z")["selections"][0]
    assert calls == ["SPY"]
    assert updated["selection_price"] == row["selection_price"]
    assert updated["selected_at"] == row["selected_at"]
    assert updated["performance"]["benchmark"]["status"] == "MATCHED"
    calls.clear()
    refresh(path,loader,now="2027-11-02T12:00Z")
    assert calls == []
