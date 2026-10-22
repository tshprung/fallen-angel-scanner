import json
from pathlib import Path

import pandas as pd
import pytest

from paper_tracking import assess_selection, record_selections, refresh


def stock(ticker="AAA"):
    return {"ticker": ticker, "currency": "USD", "current_price": 100, "bucket": "fallen_angel"}


def selection():
    return {"selected_at": "2026-10-21T18:30:00Z", "ticker": "AAA"}


def history(dates, opens, closes):
    return pd.DataFrame({"Open": opens, "Close": closes}, index=pd.to_datetime(dates))


def test_no_entry_on_selection_day_and_no_incomplete_today_close():
    result = assess_selection(selection(), history(["2026-10-21", "2026-10-22"], [50, 100], [90, 200]), now="2026-10-22T20:00Z")
    assert result["status"] == "pending_next_session"


def test_next_session_open_determines_return():
    result = assess_selection(selection(), history(["2026-10-21", "2026-10-22", "2026-10-23"], [50, 110, 120], [100, 120, 132]), now="2026-10-24T12:00Z")
    assert result["entry_session"] == "2026-10-22"
    assert result["return_local_pct"] == pytest.approx(20)


def test_unavailable_ticker_is_unverified_not_deleted_or_assumed_zero_return():
    assert assess_selection(selection(), None)["status"] == "unverified"


def test_missing_first_open_does_not_move_entry_to_a_more_favorable_day():
    frame = history(["2026-10-22", "2026-10-23"], [float("nan"), 100], [90, 150])
    assert assess_selection(selection(), frame, now="2026-10-24T12:00Z")["status"] == "unverified"


def test_split_adjusted_prices_produce_consistent_return():
    # Both historical entry and exit reflect the same split adjustment.
    result = assess_selection(selection(), history(["2026-10-22", "2026-10-23"], [50, 55], [50, 60]), now="2026-10-24T12:00Z")
    assert result["return_local_pct"] == pytest.approx(20)


def test_stale_prices_do_not_claim_completed_twelve_month_result():
    result = assess_selection(selection(), history(["2026-10-22"], [100], [120]), now="2027-11-01T12:00Z")
    assert result["status"] == "stale_unverified"
    assert result["ended_2x"] is None


def test_touching_double_is_distinct_from_ending_double():
    frame = history(["2026-10-22", "2027-03-01", "2027-10-22", "2027-10-25"], [100, 210, 150, 300], [100, 220, 150, 300])
    result = assess_selection(selection(), frame, now="2027-10-26T12:00Z")
    assert result["status"] == "complete_12m"
    assert result["mark_session"] == "2027-10-22"
    assert result["touched_2x_at_close"]
    assert not result["ended_2x"]
    assert result["return_local_pct"] == pytest.approx(50)


def test_daily_snapshots_are_idempotent_and_immutable(tmp_path):
    path = tmp_path / "ledger.json"
    first = stock()
    first["goal_fit"] = {"status": "RESEARCH_WATCH", "record_id": None}
    record_selections([first], path, now="2026-10-21T18:30Z")
    first["current_price"] = 200
    first["goal_fit"] = {"status": "DOCUMENTED_12M_CASE", "record_id": "fixture"}
    data = record_selections([first], path, now="2026-10-21T19:30Z")
    assert len(data["selections"]) == 1
    assert data["selections"][0]["selection_price"] == 100
    assert data["selections"][0]["goal_fit"]["status"] == "RESEARCH_WATCH"
    data = record_selections([first], path, now="2026-10-22T18:30Z")
    assert len(data["selections"]) == 2
    assert data["selections"][1]["goal_fit"]["status"] == "DOCUMENTED_12M_CASE"


def test_refresh_retains_failed_histories_and_fetches_each_ticker_once(tmp_path):
    path = tmp_path / "ledger.json"
    record_selections([stock()], path, now="2026-10-21T18:30Z")
    record_selections([stock()], path, now="2026-10-22T18:30Z")
    calls = []
    def loader(ticker, start):
        calls.append(ticker)
        raise RuntimeError("provider unavailable")
    refresh(path, loader, now="2026-10-24T12:00Z")
    assert calls == ["AAA"]
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["selections"]) == 2
    assert all(s["performance"]["status"] == "unverified" for s in data["selections"])
