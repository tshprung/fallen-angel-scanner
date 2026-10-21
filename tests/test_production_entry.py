def test_production_import_does_not_download_the_universe_and_does_not_soften_risk(monkeypatch):
    import requests
    from unittest.mock import Mock
    network = Mock(side_effect=AssertionError("Importing the CLI must not perform a scan"))
    monkeypatch.setattr(requests, "get", network)
    import scanner_entry
    scanner = scanner_entry.scanner
    health = {"debt_to_equity": .5, "current_ratio": 1.2,
              "cash": 0, "revenue": 1, "market_cap": 1}
    assert scanner.calculate_risk_score(health, "UNCLEAR") == 4
    assert network.call_count == 0


def test_legacy_minor_currency_baseline_cannot_generate_an_ambiguous_alert(monkeypatch):
    import pandas as pd
    from types import SimpleNamespace
    import scanner_enhanced as enhanced
    stock = SimpleNamespace(info={"currency": "GBp"},
        history=lambda **kwargs: pd.DataFrame({"Close": [40.]}), splits=pd.Series(dtype=float))
    monkeypatch.setattr(enhanced.yf, "Ticker", lambda _: stock)
    assert enhanced._safe_check_price_alerts({"tracked_prices": {"AAA.L": {"price": 100, "date": "2026-10-20"}}}) == []


def test_same_day_reverse_split_is_not_reapplied_to_a_legacy_close_baseline(monkeypatch):
    import pandas as pd
    from types import SimpleNamespace
    import scanner_enhanced as enhanced
    stock = SimpleNamespace(info={"currency": "USD"},
        history=lambda **kwargs: pd.DataFrame({"Close": [95.]}),
        splits=pd.Series([.5], index=pd.to_datetime(["2026-10-21T09:30Z"])))
    monkeypatch.setattr(enhanced.yf, "Ticker", lambda _: stock)
    assert enhanced._safe_check_price_alerts({"tracked_prices": {"AAA": {"price": 100, "date": "2026-10-21"}}}) == []


def test_split_after_the_recorded_baseline_preserves_a_real_drop_and_quote_units(monkeypatch):
    import pandas as pd
    from types import SimpleNamespace
    import scanner_enhanced as enhanced
    stock = SimpleNamespace(info={"currency": "GBp"},
        history=lambda **kwargs: pd.DataFrame({"Close": [40.]}),
        splits=pd.Series([2.], index=pd.to_datetime(["2026-10-21T09:30Z"])))
    monkeypatch.setattr(enhanced.yf, "Ticker", lambda _: stock)
    alerts = enhanced._safe_check_price_alerts({"tracked_prices": {"AAA.L": {
        "price": 100, "currency": "GBp", "date": "2026-10-20", "recorded_at": "2026-10-20T18:30:00Z"}}})
    assert len(alerts) == 1
    assert alerts[0]["original_price"] == 50
    assert alerts[0]["currency"] == "GBp"
