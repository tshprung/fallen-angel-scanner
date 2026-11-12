import json
import runpy
import sys
from datetime import date, datetime, time, timedelta
from types import ModuleType, SimpleNamespace

import pytest

from build_quantconnect_pilot import build
from quantconnect_pilot import SIGNAL


class MarketHours:
    def get_next_market_open(self, cursor, extended):
        day = cursor.date()
        while day.weekday() >= 5 or day == date(2023, 7, 4):
            day += timedelta(days=1)
        return datetime.combine(day, time(9, 30))

    def get_next_market_close(self, opening, extended):
        hour = 13 if opening.date() == date(2023, 7, 3) else 16
        return datetime.combine(opening.date(), time(hour))


def mock_quantconnect(monkeypatch, stale_clock):
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
                return [SimpleNamespace(time=datetime(2022, 12, 16), distribution=1.5)]
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
                if stale_clock and day == date(2023, 7, 3):
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


@pytest.mark.parametrize("stale_clock", [False, True])
def test_standalone_hosted_cell_replays_or_reports_calendar_gap(stale_clock, monkeypatch, tmp_path, capsys):
    mock_quantconnect(monkeypatch, stale_clock)
    standalone = tmp_path / "research_cell.py"
    standalone.write_text(build(), encoding="utf-8")
    runpy.run_path(str(standalone))
    output = capsys.readouterr().out
    result = json.loads(output)
    assert "CTXS" not in output and "net_return" not in output and "receivable" not in output
    if stale_clock:
        assert result == {"status": "INPUT_CHECK_FAILED", "stage": "QuantConnect data mapping",
                          "error_type": "ValueError"}
    else:
        assert result["status"] == "DEVELOPMENT_ONLY"
        assert result["performance_gate"] == "INSUFFICIENT_EVIDENCE"
        assert result["input_counts"]["matched_cases"] == 3
        assert result["coverage"]["archived_event_excluded"] == 1
        assert result["strategies"]["market"] == {"ranked": 1, "fills": 1, "unresolved": 1}
        assert result["merger_cases_with_unverified_settlement"] == 1
