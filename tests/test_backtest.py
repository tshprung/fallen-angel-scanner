from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import backtest as bt
from backtest_data import Dataset
from backtest_demo import generate, snapshot
from backtest_engine import ranked_groups, scan_candidates, schedule, simulate
from fundamental_analysis import POLICY_PATH, load_policy
from screening import drawdown_candidate


def tape(n=70):
    days = [str(t.date()) for t in pd.bdate_range("2020-01-02", periods=n)]
    raw = dict(version=1, kind="synthetic", source="fixture", benchmark_security_id="M",
               sessions=[dict(date=d, open_at=d+"T14:30Z", close_at=d+"T21:00Z") for d in days],
               securities=[dict(security_id=s, issuer_id=s, currency="USD", kind=kind)
                           for s, kind in (("A", "ordinary"), ("B", "ordinary"), ("M", "benchmark"))],
               membership=[], facts=[], bars=[], actions=[])
    for sid in ("A", "B", "M"):
        raw["bars"] += [dict(security_id=sid, session=d, open=100., close=100., volume=1e6) for d in days]
    return raw, days


def event(sid, day, kind, **more):
    return dict(security_id=sid, session=day, kind=kind, available_at=day+"T14:00Z",
                source_id=f"fixture-{kind}", **more)


def fact(sid, period, published, source):
    return dict(security_id=sid, period_end=period, available_at=published, source_id=source,
                sector="Industrials", shares_outstanding=20e6, evidence=snapshot(period))


def price(raw, sid, from_day, value):
    for b in raw["bars"]:
        if b["security_id"] == sid and b["session"] >= from_day:
            b.update(open=value, close=value)


def test_statement_publication_cutoff_and_restated_vintage():
    raw, d = tape()
    raw["facts"] = [fact("A", "2019-12-31", d[0]+"T20:00Z", "old"),
                    fact("A", d[1], d[20]+"T21:01Z", "first-release"),
                    fact("A", d[1], d[22]+"T14:00Z", "restatement"),
                    fact("A", "2019-12-31", d[23]+"T14:00Z", "older-period-update")]
    data = Dataset(raw)
    assert [data.facts_at("A", i)["source_id"] for i in (20, 21, 22, 23)] == [
        "old", "first-release", "restatement", "restatement"]


def test_membership_is_dated_and_ticker_reuse_does_not_join_issuers():
    raw, d = tape()
    raw["membership"] = [
        dict(security_id=s, session=d[i], active=active, available_at=d[known]+"T14:00Z",
             ticker="REUSED", source_id=f"{s}-{i}") for s, i, known, active in
        (("A", 0, 0, True), ("A", 21, 21, False), ("B", 22, 23, True))]
    data = Dataset(raw)
    assert data.member_at("A", 20)["active"] and not data.member_at("A", 21)["active"]
    assert data.member_at("B", 22) is None and data.member_at("B", 23)["active"]
    assert data.securities["A"]["issuer_id"] != data.securities["B"]["issuer_id"]


def test_rejects_premature_full_bar_and_future_statement_period():
    raw, d = tape()
    raw["bars"][0]["close_available_at"] = d[0]+"T20:59Z"
    with pytest.raises(ValueError, match="cannot be known before close"):
        Dataset(raw)
    del raw["bars"][0]["close_available_at"]
    raw["facts"] = [fact("A", d[0], d[1]+"T14:00Z", "bad")]
    raw["facts"][0]["evidence"]["balance"]["asof"] = d[2]
    with pytest.raises(ValueError, match="future financial period"):
        Dataset(raw)


def test_signal_normalizes_split_and_special_distribution_without_future_actions():
    raw, d = tape()
    price(raw, "A", d[40], 50.)
    price(raw, "A", d[45], 30.)
    raw["actions"] = [event("A", d[40], "split", ratio=2),
                      event("A", d[45], "dividend", cash_per_share=20, pay_session=d[49]),
                      event("A", d[55], "split", ratio=.1)]
    data = Dataset(raw)
    assert set(data.signal_history("A", 39)["Close"]) == {100.}
    at_signal = data.signal_history("A", 45)
    assert at_signal["Close"].iloc[0] == 50.
    assert at_signal["Close"].iloc[-1] == 30.
    assert drawdown_candidate(at_signal, load_policy(), now=d[45]) is None
    # A revision known only after the signal may not erase that day's loss.
    raw["actions"][1]["available_at"] = d[46]+"T14:00Z"
    before_release = Dataset(raw).signal_history("A", 45)
    assert drawdown_candidate(before_release, load_policy(), now=d[45])["drop_21d_pct"] == pytest.approx(-40)


def replay(raw, *, recovery=0, cost_scale=1, config=None):
    data = Dataset(raw)
    cfg = {**bt.DEFAULTS, "initial_cash": 10000, "max_positions": 2, "min_order": 1,
           "cost_bps": {k: 0 for k in bt.DEFAULTS["cost_bps"]}, **(config or {})}
    rows = [dict(sid="A", issuer="A", adv=data.adv("A", 19))]
    return simulate(data, cfg, 19, 28, {20: (19, 26, rows)}, "scanner_core", 365, cost_scale, recovery)


def test_absent_entry_is_never_backfilled_and_capacity_uses_lagged_volume():
    raw, d = tape()
    row = next(b for b in raw["bars"] if b["security_id"] == "A" and b["session"] == d[20])
    row["open"] = None
    r = replay(raw)
    assert r["counts"]["missed_entry_open"] == 1 and r["trades"] == []
    row.update(open=100, volume=0)
    r = replay(raw, config={"participation": .00002})
    assert r["trades"][0]["initial_notional"] == pytest.approx(2000)
    assert r["trades"][0]["entry_session"] == d[20]


def test_split_dividend_receivable_and_spinoff_reconcile_nav():
    raw, d = tape()
    raw["actions"] = [event("A", d[21], "split", ratio=2),
                      event("A", d[22], "dividend", cash_per_share=10, pay_session=d[25]),
                      event("A", d[23], "spin_off", successor_id="B", ratio=1)]
    price(raw, "A", d[21], 50)
    price(raw, "A", d[22], 40)
    price(raw, "A", d[23], 30)
    price(raw, "B", d[0], 10)
    r = replay(raw)
    assert [p["nav"] for p in r["daily"]] == pytest.approx([10000]*9)
    ex_day = next(p for p in r["daily"] if p["session"] == d[22])
    assert ex_day["cash"] == 5000 and ex_day["receivable"] == 1000
    assert r["trades"][0]["net_proceeds"] == pytest.approx(5000)


@pytest.mark.parametrize("cash,successor,ratio", [(100, None, None), (20, "B", .5)])
def test_cash_and_stock_merger_consideration(cash, successor, ratio):
    raw, d = tape()
    raw["bars"] = [b for b in raw["bars"] if b["security_id"] != "A" or b["session"] < d[22]]
    raw["actions"] = [event("A", d[22], "merger", cash_per_share=cash, successor_id=successor, ratio=ratio)]
    price(raw, "B", d[0], 160)
    r = replay(raw)
    t = r["trades"][0]
    assert t["exit_session"] == d[26 if successor else 22]
    assert t["terminal_events"] == ["merger"] and t["outcome_known"]
    assert t["net_return"] == pytest.approx(0)


@pytest.mark.parametrize("kind,cash", [("bankruptcy", 0), ("distressed_delisting", None)])
def test_distress_zero_is_distinct_from_unresolved_terminal_proceeds(kind, cash):
    raw, d = tape()
    raw["bars"] = [b for b in raw["bars"] if b["security_id"] != "A" or b["session"] < d[22]]
    raw["actions"] = [event("A", d[22], kind, cash_per_share=cash)]
    low, high = [replay(raw, recovery=r)["trades"][0] for r in (0, 1)]
    assert low["net_return"] == -1 and low["outcome_known"] == (cash == 0)
    assert high["net_return"] == (-1 if cash == 0 else 0)
    assert high["terminal_events"] == [kind]


def test_missing_planned_exit_remains_unverified_despite_later_quote():
    raw, d = tape()
    next(b for b in raw["bars"] if b["security_id"] == "A" and b["session"] == d[26])["open"] = None
    r = replay(raw, recovery=1)
    t = r["trades"][0]
    assert t["exit_session"] == d[26] and t["exit_status"] == "scenario_exit"
    assert not t["outcome_known"] and t["target_met_at_exit"] is None


def test_late_disclosed_terminal_cash_does_not_influence_an_earlier_fill():
    raw, d = tape()
    raw["bars"] = [b for b in raw["bars"] if b["security_id"] != "A" or b["session"] < d[22]]
    terminal = event("A", d[22], "ordinary_delisting", cash_per_share=100, pay_session=d[24])
    terminal["available_at"] = d[24]+"T20:00Z"
    raw["actions"] = [terminal]
    cfg = {**bt.DEFAULTS, "initial_cash": 10000, "max_positions": 2, "min_order": 1,
           "cost_bps": {k: 0 for k in bt.DEFAULTS["cost_bps"]}}
    orders = {20: (19, 26, [dict(sid="A", issuer="A", adv=1e8)]),
              23: (22, 26, [dict(sid="B", issuer="B", adv=1e8)])}
    for value in (100, 1000):
        terminal["cash_per_share"] = value
        r = simulate(Dataset(raw), cfg, 19, 28, orders, "scanner_core", 365, 1, 0)
        assert r["trades"][1]["initial_notional"] == pytest.approx(2500)
        assert next(x for x in r["daily"] if x["session"] == d[23])["provisional_mark"]
        disclosed = next(x for x in r["daily"] if x["session"] == d[24])
        assert disclosed["receivable"] == 50*value


def test_transaction_costs_reduce_nav_under_base_and_stress():
    raw, _ = tape()
    cfg = {"cost_bps": {k: 10 for k in bt.DEFAULTS["cost_bps"]}}
    base, stress = [replay(raw, cost_scale=x, config=cfg) for x in (1, 2)]
    assert 0 < base["costs"] < stress["costs"]
    assert stress["daily"][-1]["nav"] < base["daily"][-1]["nav"] < 10000
    assert base["daily"][-1]["nav"] == pytest.approx(10000-base["costs"])


def test_matched_control_excludes_core_issuer_and_respects_calipers():
    core = dict(sid="A", issuer="A", sector="Industrials", cap=1e9, adv=1e8,
                quality=True, value=50, shock={"drop_recent_peak_pct": -30})
    same_issuer = {**core, "sid": "A2", "shock": None}
    too_illiquid = {**core, "sid": "B", "issuer": "B", "adv": 1e6, "shock": None}
    match = {**core, "sid": "C", "issuer": "C", "cap": 1.2e9, "shock": None}
    groups = ranked_groups([core, same_issuer, too_illiquid, match], bt.DEFAULTS)
    assert [r["sid"] for r in groups["scanner_core"]] == ["A"]
    assert [r["sid"] for r in groups["matched"]] == ["C"]
    assert groups["matched"][0]["matched_to"] == "A"
    assert {r["sid"] for r in groups["value_quality"]} == {"A", "A2", "B", "C"}


def test_later_clearance_cannot_admit_a_stock_at_earlier_signal():
    raw, d = tape()
    price(raw, "A", d[40], 60.)
    raw["membership"] = [dict(security_id="A", session=d[0], active=True, ticker="A",
                              source_id="active", available_at=d[0]+"T14:00Z")]
    held = fact("A", d[30], d[35]+"T20:00Z", "held")
    held.update(filing_status="REVIEW_REQUIRED", event_hold=True)
    clearance = {**held, "source_id": "cleared", "available_at": d[40]+"T21:01Z",
                 "filing_status": "METADATA_CHECKED", "event_hold": False}
    raw["facts"] = [held, clearance]
    data = Dataset(raw)
    policy = load_policy()
    before, counts = scan_candidates(data, 40, bt.DEFAULTS, policy)
    assert before[0]["shock"] and not before[0]["quality"]
    assert counts["archived_event_excluded"] == 1 and counts["input_unverified_members"] == 0
    after, _ = scan_candidates(data, 41, bt.DEFAULTS, policy)
    assert after[0]["shock"] and after[0]["quality"]


def test_purge_signals_whose_planned_exit_crosses_fold_boundary():
    raw, _ = tape(320)
    data = Dataset(raw)
    first, stop, eligible = schedule(data, data.days[20], data.days[290], 183, 21)
    assert first == 20 and stop == 291 and eligible
    assert all(data.days[exit_i] >= data.days[i+1]+timedelta(days=183) and exit_i < stop
               for i, exit_i in eligible.items())
    assert max(eligible) < 200


def test_paired_block_interval_is_reproducible_and_suppresses_short_samples():
    cfg = deepcopy(bt.DEFAULTS)
    cfg["acceptance"]["min_independent_blocks"] = 4
    def result(n, rate):
        return {"daily": [{"nav": float(v)} for v in (1+rate)**np.arange(n)]}
    assert bt.paired_comparison(result(200, .001), result(200, .0005), 183, cfg)["interval"] is None
    comp = bt.paired_comparison(result(580, .001), result(580, .0005), 183, cfg)
    assert comp["interval"][0] > 0
    assert comp["interval"] == pytest.approx([comp["annualized_net_excess"]]*2)


def test_frozen_synthetic_run_exercises_all_strategies_without_claiming_edge(tmp_path):
    demo, report_path = tmp_path/"demo", tmp_path/"report"
    generate(demo)
    args = (demo/"dataset.json", demo/"protocol.json", POLICY_PATH, demo/"lock.json")
    report = bt.run(*args, "holdout", report_path)
    assert report["status"] == "SYNTHETIC_ONLY"
    assert set(report["horizons"]) == {"183", "365", "730"}
    metrics = report["horizons"]["365"]["scenarios"][0]["metrics"]
    assert set(metrics) == set(bt.STRATEGIES) and all(m["completed_trades"] > 0 for m in metrics.values())
    # Any post-freeze change, even if it doesn't affect parsing, is rejected.
    path = Path(args[1])
    with path.open("a", encoding="utf-8") as f:
        f.write("\n")
    with pytest.raises(ValueError, match="lock does not match"):
        bt.run(*args, "holdout", tmp_path/"changed")
    assert not (tmp_path/"changed").exists()
