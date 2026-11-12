import json
import runpy
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from build_quantconnect_pilot import build
from quantconnect_cohort import ANCHORS, SHARES, run_cohort_audit
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


def mock_quantconnect(monkeypatch, problem, universe_rows=None):
    class TradeBar:
        pass

    class Split:
        pass

    class Dividend:
        pass

    class Delisting:
        pass

    hours = MarketHours()

    class History:
        def __getitem__(self, kind):
            return lambda symbol, start, end, *resolution: self.read(kind, symbol, start, end)

        def read(self, kind, symbol, start, end):
            if kind is Dividend and symbol.value == "SPY":
                return [SimpleNamespace(time=datetime.fromisoformat(day),
                                        distribution=1.5 if problem == "amount" and day == "2022-12-16"
                                        else round(amount, 2))
                        for day, (_, amount) in SPY_DISTRIBUTIONS.items()
                        if problem != "missing" or day != "2023-06-16"]
            if kind is Delisting and symbol.value == "CTXS":
                return [SimpleNamespace(time=datetime(2022, 9, 30), price=0)]
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
                result.append(SimpleNamespace(time=opening, end_time=close, open=100, close=100, volume=1_000_000))
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
            return self.add_equity(symbol.value, resolution, **kwargs)

        def add_universe(self, selection):
            return selection

        def universe_history(self, universe, start, end):
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


def test_cohort_audit_requires_original_members_and_keeps_unverified_names_visible(monkeypatch, tmp_path, capsys):
    tickers = sorted(ANCHORS) + [f"STOCK{i}" for i in range(18)]
    rows = [SimpleNamespace(symbol=SimpleNamespace(value=ticker, id=f"{ticker} ID"),
                            company_reference=SimpleNamespace(cik=("1744676" if ticker == "TME" else
                                                                  SHARES.get(ticker, ("7",))[0])))
            for ticker in tickers]
    mock_quantconnect(monkeypatch, None, rows)
    files = build()
    for name, source in files.items():
        (tmp_path / name).write_bytes(source.encode("utf-8"))
    monkeypatch.syspath_prepend(str(tmp_path))
    cohort = [row.symbol for row in rows[:32]]
    try:
        cell = Path(__file__).resolve().parents[1] / "quantconnect_cohort.py"
        runpy.run_path(str(cell), init_globals={"selected_ids": cohort}, run_name="__main__")
        result = json.loads(capsys.readouterr().out)
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
        assert "EXLS" not in json.dumps(result)

        alternate = cohort[:-1] + [rows[-1].symbol]
        assert run_cohort_audit({"original_selection": cohort, "other_sample": alternate}) == {
            "status": "ORIGINAL_SAMPLE_NOT_IDENTIFIED"}
        assert run_cohort_audit({"cohort_ids": [symbol.value for symbol in cohort]}) == {
            "status": "ORIGINAL_SAMPLE_NOT_IDENTIFIED"}
        assert not capsys.readouterr().out
    finally:
        for name in files:
            sys.modules.pop(name.removesuffix(".py"), None)
