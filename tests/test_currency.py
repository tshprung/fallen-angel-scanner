from unittest.mock import Mock

import pandas as pd
import pytest

from scanner_currency import (CurrencyUnavailable, FxRates, currency_context,
                              market_cap_usd, leverage_info_usd, normalize_health)
from scanner_history import price_history
import fallen_angel_scanner as scanner


def fx_rates():
    rates = {"GBPUSD=X": 1.25, "PLNUSD=X": .25, "ILSUSD=X": .27, "EURUSD=X": 1.1}
    loader = Mock(side_effect=lambda pair: pd.DataFrame({"Close": [rates[pair]]}, index=pd.to_datetime(["2026-10-20"], utc=True)))
    return FxRates(loader, now="2026-10-21T12:00Z"), loader


@pytest.mark.parametrize("currency,scale,rate", [("USD", 1, 1), ("GBP", 1, 1.25), ("GBp", .01, 1.25), ("GBX", .01, 1.25), ("PLN", 1, .25), ("ILA", .01, .27), ("EUR", 1, 1.1)])
def test_quote_units_and_fx(currency, scale, rate):
    fx, _ = fx_rates()
    context = currency_context({"currency": currency}, fx)
    assert context["quote_to_usd"] == pytest.approx(scale * rate)


@pytest.mark.parametrize("cap", [1_000_000_000, 100_000_000_000])
def test_minor_market_cap_units_are_resolved_from_shares(cap):
    fx, _ = fx_rates()
    info = {"currency": "GBp", "marketCap": cap, "sharesOutstanding": 100_000_000, "regularMarketPrice": 1000}
    assert market_cap_usd(info, currency_context(info, fx)) == pytest.approx(1_250_000_000)


def test_unverifiable_minor_market_cap_fails_closed():
    fx, _ = fx_rates()
    info = {"currency": "ILA", "marketCap": 1e9}
    with pytest.raises(CurrencyUnavailable):
        market_cap_usd(info, currency_context(info, fx))


def test_fx_caches_successes_and_failures():
    fx, loader = fx_rates()
    fx.rate("GBP")
    fx.rate("GBP")
    assert loader.call_count == 1
    for _ in range(2):
        with pytest.raises(CurrencyUnavailable):
            fx.rate("JPY")
    assert loader.call_count == 2


@pytest.mark.parametrize("date,value", [("2026-09-01", 1.2), ("2026-10-22", 1.2), ("2026-10-20", float("nan")), ("2026-10-20", float("inf")), ("2026-10-20", -1)])
def test_stale_future_and_invalid_fx_are_rejected(date, value):
    fx = FxRates(lambda _: pd.DataFrame({"Close": [value]}, index=pd.to_datetime([date], utc=True)), now="2026-10-21T12:00Z")
    with pytest.raises(CurrencyUnavailable):
        fx.rate("GBP")


def test_cross_currency_financials_have_consistent_cash_and_debt_ratios():
    fx, _ = fx_rates()
    info = {"currency": "PLN", "financialCurrency": "EUR", "marketCap": 4e9, "totalDebt": 2e9, "totalCash": 1e9}
    usd = leverage_info_usd(info, currency_context(info, fx), fx)
    health = normalize_health({"cash": 1e9, "revenue": 2e9, "net_debt": 1e9, "total_debt": 2e9}, usd)
    assert health["market_cap"] == pytest.approx(1e9)
    assert health["net_debt"] / health["market_cap"] == pytest.approx(1.1)
    assert health["cash"] == pytest.approx(1.1e9)
    assert info["marketCap"] == 4e9


def test_missing_financial_currency_cannot_be_treated_as_quote_currency():
    fx, _ = fx_rates()
    info = {"currency": "USD", "marketCap": 1e9}
    with pytest.raises(CurrencyUnavailable):
        leverage_info_usd(info, currency_context(info, fx), fx)


def test_liquidity_threshold_uses_usd_including_minor_units():
    history = pd.DataFrame({"Close": [1000.] * 20, "Volume": [100000.] * 20})
    assert scanner.passes_avg_dollar_liquidity(history, 1e6, .0125)
    assert not scanner.passes_avg_dollar_liquidity(history, 2e6, .0125)


def test_repair_major_units_are_restored_to_quote_units_without_changing_volume():
    ticker = Mock()
    ticker.info = {"currency": "GBp"}
    ticker.history_metadata = {"currency": "GBP"}
    ticker.history.return_value = pd.DataFrame({"Close": [10.], "Volume": [1000]})
    history = price_history(ticker)
    assert history["Close"].iloc[0] == 1000
    assert history["Volume"].iloc[0] == 1000
    assert ticker.history.return_value["Close"].iloc[0] == 10


@pytest.mark.parametrize("currency", [None, "UNKNOWN"])
def test_missing_or_unknown_quote_currency_is_not_assumed_usd(currency):
    with pytest.raises(CurrencyUnavailable):
        currency_context({"currency": currency})


def test_minor_price_display_preserves_units():
    assert scanner.format_price_for_email(1000, "GBp") == "1000.00 GBp"
    assert scanner.format_price_for_email(1000, "ILA") == "1000.00 ILA"


def test_stage1_rejects_local_cap_that_only_appears_to_clear_usd_floor(monkeypatch):
    fx, _ = fx_rates()
    info = {"currency": "PLN", "marketCap": 1e9, "currentPrice": 10}
    monkeypatch.setattr(scanner, "get_all_tickers", lambda: ["AAA.WA"])
    monkeypatch.setattr(scanner, "load_failed_tickers", lambda: {})
    monkeypatch.setattr(scanner, "save_failed_tickers", lambda _: None)
    monkeypatch.setattr(scanner, "get_stock_with_retry", lambda _: (Mock(), info))
    monkeypatch.setattr(scanner, "currency_context", lambda data: currency_context(data, fx))
    monkeypatch.setattr(scanner, "get_min_market_cap_usd", lambda _: 400e6)
    assert scanner.stage1_quick_filter()[0] == []  # PLN 1B = USD 250M


def test_stage2_converts_financials_before_leverage_gate(monkeypatch):
    fx, _ = fx_rates()
    info = {"currency": "PLN", "financialCurrency": "EUR", "marketCap": 4e9,
            "totalDebt": 3e9, "totalCash": 1e9, "totalStockholderEquity": 10e9}
    captured = []
    monkeypatch.setattr(scanner, "get_stock_with_retry", lambda _: (Mock(), info))
    monkeypatch.setattr(scanner, "should_send_stock", lambda *args: True)
    monkeypatch.setattr(scanner, "is_biotechnology_company", lambda _: False)
    monkeypatch.setattr(scanner, "profitability_signals", lambda _: (0, False))
    monkeypatch.setattr(scanner, "currency_context", lambda data: currency_context(data, fx))
    monkeypatch.setattr(scanner, "leverage_info_usd", lambda data, context: leverage_info_usd(data, context, fx))
    def gate(normalized):
        captured.append(normalized)
        return True, "test gate"
    monkeypatch.setattr(scanner, "should_exclude_for_leverage", gate)
    assert scanner.stage2_deep_analysis([{"ticker": "AAA.WA"}], {}) == ([], [])
    assert captured[0]["marketCap"] == pytest.approx(1e9)
    assert captured[0]["totalDebt"] == pytest.approx(3.3e9)
