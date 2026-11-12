import json
import runpy
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from backtest import DEFAULTS
from backtest_data import Dataset
from backtest_demo import snapshot
from build_quantconnect_pilot import build, build_batch_cell, build_exit_check_cell
from quantconnect_batch import BATCH_SAMPLE_SIZE, batch_book, batch_sample
from quantconnect_cohort import ANCHORS, SHARES, reconcile_stock_distributions, run_cohort_audit
from quantconnect_pilot import SIGNAL, SPY_DISTRIBUTIONS, reconcile_benchmark_distributions


class MarketHours:
    def get_next_market_open(self, cursor, extended):
        day = cursor.date()
        while day.weekday() >= 5 or day == date(2023, 7, 4):
            day += timedelta(days=1)
        return datetime.combine(day, time(9, 30))

    def get_next_market_close(self, opening, extended):
        hour = 13 if opening.date() == date(2023, 7, 3) else 16
        return datetime.combine(opening.date(), time(hour))


def mock_quantconnect(monkeypatch, problem, universe_rows=None, drawdown_prices=None):
    class TradeBar:
        pass

    class Split:
        pass

    class Dividend:
        pass

    class Delisting:
        pass

    hours = MarketHours()
    stock_subscriptions = []
    cohort_replay = problem in {"cohort-reconciled", "cohort-benchmark-feed-differs"}

    class History:
        def __getitem__(self, kind):
            return lambda symbol, start, end, *resolution: self.read(kind, symbol, start, end)

        def read(self, kind, symbol, start, end):
            if cohort_replay and symbol.value == "SPY" and stock_subscriptions:
                raise ValueError("Benchmark history requested after loading stock subscriptions")
            if kind is Dividend and symbol.value == "SPY":
                dividends = {day: round(amount, 2) for day, (_, amount) in SPY_DISTRIBUTIONS.items()}
                if problem in {"missing", "cohort-benchmark-feed-differs"}:
                    del dividends["2023-06-16"]
                if problem in {"amount", "cohort-benchmark-feed-differs"}:
                    dividends["2022-12-16"] = 1.5
                rows = list(dividends.items())
                if problem == "cohort-benchmark-feed-differs":
                    rows.extend([("2023-06-20", 1.64), ("2023-03-17", 1.51)])
                return [SimpleNamespace(time=datetime.fromisoformat(day), distribution=amount)
                        for day, amount in rows]
            if kind is Dividend and symbol.value == "MRTN" and universe_rows is not None:
                return [SimpleNamespace(time=datetime.fromisoformat(day), distribution=cash)
                        for day, cash in [("2022-07-01", .06), ("2022-12-12", .06), ("2023-03-16", .10)]]
            if kind is Dividend and symbol.value == "XRX" and cohort_replay:
                return [SimpleNamespace(time=datetime(2023, 6, 29), distribution=.25)]
            if kind is Delisting and symbol.value == "CTXS":
                return [SimpleNamespace(time=datetime(2022, 9, 30), price=0)]
            if kind is Delisting and symbol.value == "LATE" and start < datetime(2023, 4, 4) < end:
                return [SimpleNamespace(time=datetime(2023, 4, 4), price=0)]
            if kind is not TradeBar:
                return []
            result = []
            cursor = start
            while cursor < end:
                opening = hours.get_next_market_open(cursor, False)
                day = opening.date()
                if opening >= end or (symbol.value == "CTXS" and day >= date(2022, 9, 30)):
                    break
                close = hours.get_next_market_close(opening, False)
                if problem == "clock" and day == date(2023, 7, 3):
                    close = datetime.combine(day, time(16))
                price = (drawdown_prices or {}).get(symbol.value, 100)
                crash = date(2022, 9, 15) if problem == "batch" else date(2022, 6, 16)
                if symbol.value in (drawdown_prices or {}) and day < crash:
                    price /= .65
                result.append(SimpleNamespace(time=opening, end_time=close, open=price, close=price, volume=1_000_000))
                cursor = datetime.combine(day+timedelta(days=1), time.min)
            return result

    class QuantBook:
        def __init__(self):
            self.settings = SimpleNamespace()
            self.history = History()

        def set_start_date(self, *args):
            pass

        def add_equity(self, ticker, resolution, **kwargs):
            assert self.settings.daily_precise_end_time and kwargs["fill_forward"] is False
            assert kwargs["data_normalization_mode"] == "raw"
            return SimpleNamespace(symbol=SimpleNamespace(value=ticker, id=ticker),
                                   exchange=SimpleNamespace(hours=hours))

        def add_security(self, symbol, resolution, **kwargs):
            stock_subscriptions.append(symbol.value)
            return self.add_equity(symbol.value, resolution, **kwargs)

        def add_universe(self, selection):
            return selection

        def universe_history(self, universe, start, end):
            if problem == "batch":
                return {("universe", end): universe_rows}
            assert start.date() < end.date() == SIGNAL
            if universe_rows is not None:
                return {("universe", datetime.combine(SIGNAL, time.min)): universe_rows}
            rows = [SimpleNamespace(symbol=SimpleNamespace(value=ticker, id=f"{ticker} ID"),
                                    company_reference=SimpleNamespace(cik=cik))
                    for ticker, cik in (("EXLS", "0001297989"), ("MRTN", "799167"), ("CTXS", "877890"),
                                        ("CTXS", "12345"))]
            return {(None, end): rows}

    api = ModuleType("AlgorithmImports")
    api.DataNormalizationMode = SimpleNamespace(RAW="raw")
    api.Resolution = SimpleNamespace(DAILY="daily")
    api.SplitType = SimpleNamespace(SPLIT_OCCURRED="occurred")
    for kind in (TradeBar, Split, Dividend, Delisting):
        setattr(api, kind.__name__, kind)
    research = ModuleType("QuantConnect.Research")
    research.QuantBook = QuantBook
    monkeypatch.setitem(sys.modules, "AlgorithmImports", api)
    monkeypatch.setitem(sys.modules, "QuantConnect.Research", research)


@pytest.mark.parametrize("problem", [None, "clock", "missing", "amount"])
def test_hosted_modules_replay_or_reject_input_mismatch(problem, monkeypatch, tmp_path, capsys):
    mock_quantconnect(monkeypatch, problem)
    files = build()
    for name, source in files.items():
        (tmp_path / name).write_bytes(source.encode("utf-8"))
    monkeypatch.syspath_prepend(str(tmp_path))
    notebook_cell = tmp_path / "research_cell.py"
    notebook_cell.write_text("import json\nfrom fa_pilot_replay import run_quantconnect_pilot\n"
                             "print(json.dumps(run_quantconnect_pilot(), indent=2))\n", encoding="utf-8")
    try:
        runpy.run_path(str(notebook_cell))
    finally:
        for name in files:
            sys.modules.pop(name.removesuffix(".py"), None)
    output = capsys.readouterr().out
    result = json.loads(output)
    assert "CTXS" not in output and "net_return" not in output and "receivable" not in output
    if problem in {"clock", "missing"}:
        assert result == {"status": "INPUT_CHECK_FAILED", "stage": "QuantConnect data mapping",
                          "error_type": "ValueError"}
    else:
        assert result["status"] == "DEVELOPMENT_ONLY"
        assert result["performance_gate"] == "INSUFFICIENT_EVIDENCE"
        assert result["input_counts"]["matched_cases"] == 3
        assert result["input_counts"]["benchmark_distributions_reconciled"] == 9
        assert result["input_counts"]["benchmark_amount_disagreements"] == (1 if problem == "amount" else 0)
        assert result["input_counts"]["unverified_payment_dates"] == 1
        assert result["coverage"]["archived_event_excluded"] == 1
        assert result["strategies"]["market"] == {"ranked": 1, "fills": 1, "unresolved": 0}
        assert result["merger_cases_with_unverified_settlement"] == 1


def test_benchmark_distribution_uses_sponsor_amount_and_waits_until_after_payment():
    dividends = [dict(kind="dividend", session=day, cash_per_share=round(amount, 2), pay_session=None)
                 for day, (_, amount) in SPY_DISTRIBUTIONS.items()]
    next(row for row in dividends if row["session"] == "2022-12-16")["cash_per_share"] = 1.5
    reconciled, amount_disagreements = reconcile_benchmark_distributions(dividends, MarketHours())
    verified = {row["session"]: row for row in reconciled}
    assert amount_disagreements == 1
    assert verified["2022-12-16"]["cash_per_share"] == 1.781400
    assert verified["2022-12-16"]["pay_session"] == "2023-02-01"
    assert verified["2023-03-17"]["pay_session"] == "2023-05-01"  # April 28 was a Friday.
    assert verified["2023-06-16"]["pay_session"] == "2023-08-01"  # Cash remains outside the pilot window.


@pytest.mark.parametrize("problem", [None, "cohort-reconciled", "cohort-benchmark-feed-differs"])
def test_cohort_audit_requires_original_members_and_complete_outcomes(problem, monkeypatch, tmp_path, capsys):
    tickers = sorted(ANCHORS) + [f"STOCK{i}" for i in range(18)]
    rows = [SimpleNamespace(symbol=SimpleNamespace(value=ticker, id=f"{ticker} ID"),
                            company_reference=SimpleNamespace(cik=("1744676" if ticker == "TME" else
                                                                  SHARES.get(ticker, ("7",))[0])))
            for ticker in tickers]
    complete_stock_inputs = problem is not None
    shocks = {"MFC": 65, "XRX": 15, "SEM": 65} if complete_stock_inputs else {
        "EXLS": 65, "MRTN": 65, "CTXS": 65, "MFC": 65, "MSA": 65, "XRX": 15}
    mock_quantconnect(monkeypatch, problem, rows, shocks)
    files = build()
    for name, source in files.items():
        (tmp_path / name).write_bytes(source.encode("utf-8"))
    monkeypatch.syspath_prepend(str(tmp_path))
    cohort = [row.symbol for row in rows[:32]]
    try:
        result = run_cohort_audit({"cohort_ids": cohort})
        assert result["status"] == "DEVELOPMENT_COVERAGE_ONLY"
        assert result["sample_size"] == 32
        assert result["performance_gate"] == "INSUFFICIENT_EVIDENCE"
        counts = result["coverage"]
        assert counts["documented_ads"] == 1
        assert counts["share_basis_unverified"] == 20
        assert counts["passed_verified_common_floors"] == 11
        assert counts["mapped_quality_inputs"] == 1
        assert counts["known_filing_hold"] == 1
        assert counts["quality_inputs_unverified"] == 9
        assert counts["securities_with_delisting_notices"] == counts["horizon_open_missing"] == 1
        assert counts["delisting_notices_without_verified_terms"] == 0
        assert counts["stock_dividends_reconciled"] == (2 if complete_stock_inputs else 1)
        assert counts["stock_dividend_amount_disagreements"] == 1
        assert counts["stock_distributions_with_unknown_payment"] == 2
        assert counts["holding_window_distributions_with_unknown_payment"] == 1
        assert counts["drawdown_signals"] == (3 if complete_stock_inputs else 6)
        checks = {
            "net_debt_at_least_market_cap": 1, "nonpositive_trailing_free_cash_flow": 1,
            "specialist_review_required": 1,
        }
        if not complete_stock_inputs:
            checks.update(failed_mapped_quality_checks=1, filing_hold=1, valuation_upper_bound_below_target=1)
        assert result["drawdown_financial_checks"] == checks
        remaining = int(not complete_stock_inputs)
        assert result["drawdown_outcome_gaps"] == {
            "delisting_notice_without_verified_terms": 0, "entry_open_missing": 0, "horizon_open_missing": remaining,
            "merger_payment_unverified": remaining, "stocks_with_unknown_dividend_payments": remaining,
            "unknown_dividend_payments": remaining,
        }
        assert "EXLS" not in json.dumps(result)
        replay = result["cohort_replay"]
        assert replay["scanner_core_qualified_signals"] == 0
        if complete_stock_inputs:
            assert replay["status"] == "DEVELOPMENT_REPLAY_ONLY"
            drawdown = replay["strategies"]["drawdown_only"]
            market = replay["strategies"]["market"]
            assert drawdown["ranked"] == drawdown["fills"] == 3
            assert market["ranked"] == market["fills"] == 1
            assert drawdown["unresolved"] == market["unresolved"] == 0
            assert drawdown["entry_capital_used_pct"] == pytest.approx(30, abs=.01)
            assert market["entry_capital_used_pct"] == pytest.approx(100, abs=.01)
            # Flat raw prices. The receivable after exit raises the small
            # drawdown portfolio's NAV, and SPY earns its four distributions.
            assert 0 < drawdown["net_portfolio_return_pct"] < market["net_portfolio_return_pct"]
            assert market["net_portfolio_return_pct"] == pytest.approx(5.8639)
            difference = int(problem == "cohort-benchmark-feed-differs")
            assert replay["benchmark_distributions"] == {
                "sponsor_distributions": 4, "missing_feed_dates": difference, "unexpected_feed_dates": difference,
                "duplicate_feed_rows": difference, "feed_amount_disagreements": difference,
            }
        else:
            assert replay["status"] == "DRAWDOWN_OUTCOME_INPUTS_INCOMPLETE"
            assert "strategies" not in replay

        alternate = cohort[:-1] + [rows[-1].symbol]
        assert run_cohort_audit({"original_selection": cohort, "other_sample": alternate}) == {
            "status": "ORIGINAL_SAMPLE_NOT_IDENTIFIED"}
        assert run_cohort_audit({"cohort_ids": [symbol.value for symbol in cohort]}) == {
            "status": "ORIGINAL_SAMPLE_NOT_IDENTIFIED"}
        assert not capsys.readouterr().out
    finally:
        for name in files:
            sys.modules.pop(name.removesuffix(".py"), None)


def test_stock_distribution_requires_matching_security_and_defers_cash_past_payable_day():
    dividend = dict(session="2023-03-16", kind="dividend", cash_per_share=.06, pay_session=None)
    actions, counts = reconcile_stock_distributions([dividend], "MRTN", "799167", MarketHours())
    assert counts["stock_dividends_reconciled"] == 1
    assert actions[0]["pay_session"] == "2023-04-03"
    assert dividend["pay_session"] is None
    assert reconcile_stock_distributions([dividend], "MRTN", "7", MarketHours()) == ([dividend], {})
    assert reconcile_stock_distributions([dividend], "OTHER", "799167", MarketHours()) == ([dividend], {})


def test_cohort_xerox_dividend_retains_cash_date_after_horizon_exit():
    dividend = dict(session="2023-06-29", kind="dividend", cash_per_share=.25, pay_session=None)
    actions, counts = reconcile_stock_distributions([dividend], "XRX", "1770450", MarketHours())
    assert counts == {"stock_dividends_reconciled": 1}
    assert actions[0]["pay_session"] == "2023-08-01"
    assert dividend["session"] < "2023-07-03" < actions[0]["pay_session"]


def test_cohort_manulife_uses_gross_usd_and_does_not_accept_cad_amount():
    usd_dividend = dict(session="2023-05-23", kind="dividend", cash_per_share=.27, pay_session=None)
    cad_dividend = dict(usd_dividend, cash_per_share=.365)
    actions, counts = reconcile_stock_distributions(
        [usd_dividend, cad_dividend], "MFC", "1086888", MarketHours()
    )
    assert counts == {"stock_dividends_reconciled": 1, "stock_dividend_amount_disagreements": 1}
    assert actions[0]["cash_per_share"] == .268521
    assert actions[0]["pay_session"] == "2023-06-20"
    assert actions[1] == cad_dividend


def test_generated_development_batch_keeps_missing_evidence_and_delisting_outcomes_visible(
    monkeypatch, tmp_path, capsys
):
    common = SimpleNamespace(security_type="ST00000001", currency_id="USD",
                             is_depositary_receipt=False, is_primary_share=True)
    names = ["DROP", "LATE", *[f"STOCK{i}" for i in range(14)]]
    universe = [SimpleNamespace(symbol=SimpleNamespace(value=name, id=f"{name} ID"),
                                company_reference=SimpleNamespace(cik=str(i)),
                                market_cap=2e9, security_reference=common)
                for i, name in enumerate(names, 1)]
    mock_quantconnect(monkeypatch, "batch", universe, {"DROP": 60, "LATE": 60})
    evidence = {"facts": {}}
    for i, name in enumerate(names, 1):
        evidence["facts"]["2022-09-30", name, str(i)] = dict(
            period_end="2022-06-30", available_at="2022-08-01T20:00:00Z", sector="Industrials",
            industry="Industrial Machinery", shares_outstanding=15_000_000,
            source_id=f"synthetic-filing-{i}", filing_status="METADATA_CHECKED", event_hold=False,
            evidence=snapshot("2022-06-30"),
        )
    files = build()
    for name, source in files.items():
        (tmp_path / name).write_bytes(source.encode("utf-8"))
    monkeypatch.syspath_prepend(str(tmp_path))
    cell = tmp_path / "batch_cell.py"
    cell.write_text(build_batch_cell(), encoding="utf-8")
    try:
        globals_after_run = runpy.run_path(str(cell), run_name="__main__",
                                          init_globals={"batch_verified_evidence": evidence})
    finally:
        for name in files:
            sys.modules.pop(name.removesuffix(".py"), None)
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary["status"] == "DEVELOPMENT_BATCH_ONLY"
    assert summary["performance_gate"] == "INSUFFICIENT_EVIDENCE"
    assert len(summary["dates"]) == 8
    assert "2023-09-29" in summary["dates"]
    assert "LATE" not in output
    verified = summary["dates"]["2022-09-30"]
    assert verified["verified_size_inputs"] == 16
    assert verified["core_comparison"] == "READY_FOR_DEVELOPMENT_REPLAY"
    drawdown = verified["strategies"]["drawdown_only"]
    assert drawdown["fills"] == 2
    assert drawdown["unresolved"] == 1
    assert drawdown["net_portfolio_return_pct"] is None
    assert drawdown["net_return_with_receivables_pct"] is None
    assert drawdown["outcome_gaps"] == {"delisting_notice": 1}
    detail = next(row for row in globals_after_run["batch_result"]["dates"] if row["signal_date"] == "2022-09-30")
    assert drawdown["spy_with_same_capital_pct"] > detail["market"]["net_portfolio_return_pct"] * .20
    unverified = summary["dates"]["2022-03-31"]
    assert unverified["verified_size_inputs"] == 0
    assert unverified["core_comparison"] == "INPUT_COVERAGE_INCOMPLETE"
    assert "scanner_core" not in unverified["strategies"]
    exec(build_exit_check_cell(), globals_after_run)
    exit_report = json.loads(capsys.readouterr().out)
    assert exit_report == {"status": "DEVELOPMENT_EXIT_CHECK", "orders": [
        {"ticker": "LATE", "entry_session": "2022-10-03", "exit_session": "2023-10-03",
         "delisting_notice": True, "exit_inputs": "present"}
    ]}


def test_batch_sample_is_independent_of_snapshot_order_and_limits_each_issuer_to_one_listing():
    common = SimpleNamespace(security_type="ST00000001", currency_id="USD",
                             is_depositary_receipt=False, is_primary_share=True)
    universe = [SimpleNamespace(symbol=SimpleNamespace(value=f"STOCK{i}", id=f"STOCK{i} ID"),
                                company_reference=SimpleNamespace(cik=str(i // 2 + 1)),
                                market_cap=2e9, security_reference=common)
                for i in range(40)]
    config = {"min_market_cap": 750e6}
    selected, counts = batch_sample(universe, date(2022, 9, 30), config)
    reversed_sample, reversed_counts = batch_sample(reversed(universe), date(2022, 9, 30), config)
    assert selected == reversed_sample and counts == reversed_counts
    assert counts["eligible_issuers"] == 20
    assert len({cik for _, cik, _ in selected}) == BATCH_SAMPLE_SIZE


def test_single_entry_batch_values_entitlements_without_assuming_cash_dates():
    days = [date(2022, 1, 1) + timedelta(days=i) for i in range(400)]
    days = [day.isoformat() for day in days if day.weekday() < 5]
    first = 20
    exit_i = next(i for i, day in enumerate(days) if day >= str(date.fromisoformat(days[first + 1])
                                                              + timedelta(days=365)))
    sessions = [dict(date=day, open_at=f"{day}T14:30:00Z", close_at=f"{day}T21:00:00Z") for day in days]
    stock = dict(security_id="STOCK", issuer_id="1", currency="USD", kind="ordinary")
    market = dict(security_id="SPY", issuer_id="SPY", currency="USD", kind="benchmark")
    bars = [dict(security_id="STOCK", session=day, open=149 if i == exit_i else 100,
                 close=100, volume=1_000_000) for i, day in enumerate(days)]
    ex_date = days[first + 2]
    dividend = dict(security_id="STOCK", session=ex_date, kind="dividend", cash_per_share=3.,
                    pay_session=None, available_at=f"{ex_date}T14:30:00Z", source_id="synthetic")
    raw = dict(version=1, kind="synthetic", source="entitlement test", benchmark_security_id="SPY",
               sessions=sessions, securities=[stock, market], bars=bars, membership=[], facts=[])
    orders = [dict(sid="STOCK", issuer="1", ticker="TEST", adv=100_000_000.)]
    unknown = Dataset(dict(raw, actions=[dividend]))
    confirmed = Dataset(dict(raw, actions=[dict(dividend, pay_session=days[first + 10])]))
    provisional, _ = batch_book(unknown, DEFAULTS, first, exit_i, orders, "drawdown_only", set())
    settled, _ = batch_book(confirmed, DEFAULTS, first, exit_i, orders, "drawdown_only", set())
    assert provisional["net_portfolio_return_pct"] is None
    assert provisional["unresolved"] == 1
    assert provisional["unresolved_with_receivables"] == 0
    assert provisional["net_return_with_receivables_pct"] == settled["net_portfolio_return_pct"]
    assert provisional["target_hits_with_receivables_at_exit"] == settled["target_hits_at_exit"] == 1
    assert provisional["outcome_gaps"] == {"dividend_payment_date": 1}
    conflicting, _ = batch_book(unknown, DEFAULTS, first, exit_i, orders, "drawdown_only", set(), {"STOCK"})
    assert conflicting["net_return_with_receivables_pct"] is None
    assert conflicting["outcome_gaps"] == {"dividend_payment_date": 1, "dividend_amount_conflict": 1}
    assert conflicting["outcome_review_orders"] == [
        {"ticker": "TEST", "entry_session": days[first + 1], "exit_session": days[exit_i]}
    ]
    missing_exit = Dataset(dict(raw, bars=bars[:exit_i], actions=[dividend]))
    missing, _ = batch_book(missing_exit, DEFAULTS, first, exit_i, orders, "drawdown_only", set())
    assert missing["net_return_with_receivables_pct"] is None
    assert missing["outcome_gaps"] == {"dividend_payment_date": 1, "missing_exit_open": 1}
    missing_liquidity = Dataset(dict(raw, bars=[bar for i, bar in enumerate(bars) if i != exit_i - 1],
                                     actions=[dividend]))
    no_liquidity, _ = batch_book(missing_liquidity, DEFAULTS, first, exit_i, orders, "drawdown_only", set())
    assert no_liquidity["outcome_gaps"] == {"dividend_payment_date": 1, "missing_exit_liquidity": 1}
    tight_capacity = dict(DEFAULTS, participation=.001)
    limited, _ = batch_book(unknown, tight_capacity, first, exit_i, orders, "drawdown_only", set())
    assert limited["outcome_gaps"] == {"dividend_payment_date": 1, "exit_participation_limit": 1}
