import json
from pathlib import Path

import pandas as pd
import pytest

from paper_tracking import (PERFORMANCE_VERSION, assess_selection, cohort_summary,
                            record_selections, refresh, write_report)


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
    dates = pd.bdate_range("2026-10-22", "2027-10-25")
    frame = pd.DataFrame({"Open": 100., "Close": 100.}, index=dates)
    frame.loc["2027-03-01", "Close"] = 220
    frame.loc["2027-10-22", "Close"] = 150
    frame.loc["2027-10-25", "Close"] = 300
    result = assess_selection(selection(), frame, now="2027-10-26T12:00Z")
    assert result["status"] == "complete_12m"
    assert result["mark_session"] == "2027-10-22"
    assert result["touched_2x_at_close"]
    assert not result["ended_2x"]
    assert result["touched_50pct_at_close"] and result["ended_50pct"]
    assert result["return_local_pct"] == pytest.approx(50)


def test_touching_fifty_percent_is_distinct_from_ending_there_and_from_double():
    dates = pd.bdate_range("2026-10-22", "2027-10-25")
    frame = pd.DataFrame({"Open": 100., "Close": 100.}, index=dates)
    frame.loc["2027-03-01", "Close"] = 150
    frame.loc["2027-10-22", "Close"] = 149.99
    result = assess_selection(selection(), frame, now="2027-10-26T12:00Z")
    assert result["touched_50pct_at_close"] and not result["ended_50pct"]
    assert not result["touched_2x_at_close"] and not result["ended_2x"]
    result.update(touched_2x_at_close=False)
    groups = cohort_summary({"selections": [{"ticker": "AAA", "performance": result}]})
    assert groups[0]["touched_50pct"] == 1 and groups[0]["ended_50pct"] == 0


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


def test_year_end_quote_cannot_hide_months_of_missing_prices():
    result = assess_selection(selection(), history(["2026-10-22", "2027-10-22"], [100, 200], [100, 200]),
                              now="2027-10-23T12:00Z")
    assert result["status"] == "unverified" and "gap" in result["reason"]
    assert "ended_2x" not in result and "return_local_pct" not in result


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0, -1, "missing"])
def test_bad_interior_close_cannot_disappear_from_observed_path(bad):
    result = assess_selection(selection(), history(["2026-10-22", "2026-10-23", "2026-10-26"],
                              [100, 100, 100], [100, bad, 200]), now="2026-10-27T12:00Z")
    assert result["status"] == "unverified" and "within holding window" in result["reason"]


def test_duplicate_local_session_labels_are_not_two_trading_sessions():
    frame = history(["2026-10-22T09:00Z", "2026-10-22T16:00Z"], [100, 110], [100, 120])
    result = assess_selection(selection(), frame, now="2026-10-24T12:00Z")
    assert result["status"] == "unverified" and "Duplicate" in result["reason"]


def test_contradictory_ohlc_is_unverified_in_paper_returns_too():
    frame = history(["2026-10-22", "2026-10-23"], [100, 100], [100, 50])
    frame["High"], frame["Low"] = 110, 90
    result = assess_selection(selection(), frame, now="2026-10-24T12:00Z")
    assert result["status"] == "unverified" and "OHLC" in result["reason"]


def test_bad_quotes_after_exit_do_not_change_completed_holding_window():
    dates = pd.bdate_range("2026-10-22", "2027-10-25")
    frame = pd.DataFrame({"Open": 100., "Close": 200.}, index=dates)
    frame.loc["2027-10-25", "Close"] = float("nan")
    result = assess_selection(selection(), frame, now="2027-10-26T12:00Z")
    assert result["status"] == "complete_12m" and result["ended_2x"]


def test_malformed_history_does_not_abort_assessment():
    frame = pd.DataFrame({"Open": [100], "Close": [200]}, index=["invalid date"])
    assert assess_selection(selection(), frame)["status"] == "unverified"


def test_refresh_rechecks_older_completed_method_without_changing_selection(tmp_path):
    path = tmp_path / "ledger.json"
    original = record_selections([stock()], path, now="2026-10-21T18:30Z")["selections"][0]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["selections"][0]["performance"] = {"status": "complete_12m", "ended_2x": True}
    path.write_text(json.dumps(data), encoding="utf-8")
    result = refresh(path, lambda *a: history(["2026-10-22", "2027-10-22"], [100, 200], [100, 200]),
                     now="2027-10-23T12:00Z")
    item = result["selections"][0]
    assert item["performance"]["status"] == "unverified"
    assert {k: v for k, v in item.items() if k != "performance"} == {
        k: v for k, v in original.items() if k != "performance"}


def test_current_method_completed_result_is_not_refetched(tmp_path):
    path = tmp_path / "ledger.json"
    data = record_selections([stock()], path, now="2026-10-21T18:30Z")
    performance = {"status": "complete_12m", "method_version": PERFORMANCE_VERSION, "ended_2x": False}
    data["selections"][0]["performance"] = performance
    path.write_text(json.dumps(data), encoding="utf-8")
    def forbidden(*args):
        pytest.fail("Completed current-method observation should stay frozen")
    updated = refresh(path, forbidden)["selections"][0]["performance"]
    assert {key: updated[key] for key in performance} == performance
    assert updated["benchmark"]["status"] == "UNVERIFIED"  # Missing endpoints cannot trigger a benchmark fetch.


def test_cohorts_keep_unknown_outcomes_and_separate_policy_screen_and_research_status(tmp_path):
    def item(ticker="AAA", policy="policy-v1", screen="recent_shock", research="RESEARCH_WATCH", **performance):
        return {"ticker": ticker, "selected_at": "2026-10-21T18:30Z", "policy_id": policy,
                "screen_cohort": screen, "goal_fit": {"status": research},
                "performance": dict(status="complete_12m", method_version=PERFORMANCE_VERSION,
                                    ended_2x=True, touched_2x_at_close=True, return_local_pct=100, **performance)}
    first = item()
    unknown = dict(first, ticker="FAILED", performance={"status": "unverified"})
    loss = dict(first, ticker="BBB", performance={"status": "complete_12m", "method_version": PERFORMANCE_VERSION,
                "ended_2x": False, "touched_2x_at_close": True, "return_local_pct": -25})
    old_method = dict(first, performance={"status": "complete_12m", "ended_2x": True})
    data = {"selections": [first, first, loss, unknown, old_method,
        item(policy="policy-v2"), item(screen="recent_drawdown"), item(research="DOCUMENTED_12M_CASE"),
        item(ticker="LEGACY", policy=None, screen=None, research=None)]}
    groups = cohort_summary(data)
    assert len(groups) == 5 and sum(group["observations"] for group in groups) == 9
    group = next(group for group in groups if group["observations"] == 5)
    assert group["unique_tickers"] == 3 and group["complete_12m"] == 3 and group["unverified"] == 2
    assert group["ended_2x"] == 2 and group["touched_2x"] == 3 and group["ended_loss"] == 1
    report, summary = tmp_path / "paper.md", tmp_path / "summary.json"
    write_report(data, report, summary)
    assert json.loads(summary.read_text(encoding="utf-8"))["cohorts"] == groups
    assert "not independent" in report.read_text(encoding="utf-8")
    assert "FAILED" in report.read_text(encoding="utf-8")
