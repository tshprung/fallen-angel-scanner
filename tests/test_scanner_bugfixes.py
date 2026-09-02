import numpy as np
import pandas as pd

import scanner_bugfixes as fixes


class FakeTicker:
    def __init__(self, info, balance_sheet):
        self.info = info
        self.balance_sheet = balance_sheet
        self.financials = pd.DataFrame()
        self.cashflow = pd.DataFrame()


def test_current_ratio_uses_balance_sheet_when_quote_summary_is_missing():
    bs = pd.DataFrame(
        [[2_000_000, 1_000_000], [1_000_000, 1_000_000]],
        index=["Current Assets", "Current Liabilities"],
        columns=["2026", "2025"],
    )
    ticker = FakeTicker(
        {
            "sector": "Technology",
            "industry": "Semiconductors",
            "totalCurrentAssets": None,
            "totalCurrentLiabilities": None,
            "totalDebt": 100_000,
            "totalStockholderEquity": 1_000_000,
            "totalCash": 100_000,
            "marketCap": 10_000_000,
        },
        bs,
    )

    health = fixes.get_financial_health(ticker)

    assert health["current_ratio"] == 2.0
    assert health["current_ratio"] > 0
    assert health["current_ratio_source"] == "balance_sheet"
    assert health["debt_equity_display"] == 0.1
    assert health["debt_equity_source"] == "balance_sheet"


def test_current_ratio_is_none_when_data_is_unavailable_not_zero():
    ticker = FakeTicker(
        {
            "sector": "Technology",
            "industry": "Software",
            "totalCurrentAssets": None,
            "totalCurrentLiabilities": None,
            "totalDebt": None,
            "totalStockholderEquity": None,
            "totalCash": 0,
            "marketCap": 10_000_000,
        },
        pd.DataFrame(),
    )

    health = fixes.get_financial_health(ticker)

    assert health["current_ratio"] is None
    assert health["current_ratio_source"] == "unavailable"


def test_current_yfinance_news_schema_is_parsed():
    item = {
        "content": {
            "title": "Company raises full-year guidance",
            "pubDate": "2026-09-01T10:00:00Z",
            "provider": {"displayName": "Example News"},
            "canonicalUrl": {"url": "https://example.com/story"},
        }
    }

    parsed = fixes.parse_news_item(item)

    assert parsed["title"] == "Company raises full-year guidance"
    assert parsed["publisher"] == "Example News"
    assert parsed["link"] == "https://example.com/story"
    assert parsed["timestamp"] is not None


def _fake_history(values):
    idx = pd.date_range("2021-01-01", periods=len(values), freq="B")
    return type("FakeHistory", (), {"history": lambda self, **kwargs: pd.DataFrame({"Close": values}, index=idx)})()


def test_shape_classifier_identifies_recent_break_after_stable_period():
    stable = np.linspace(100, 140, 1134)
    recent = np.linspace(140, 80, 126)
    stock = _fake_history(np.concatenate([stable, recent]))

    result = fixes.analyze_price_shape(stock, 80)

    assert result["shape"] == "sudden_drop"
    assert result["recent_drop_pct"] <= -25
    assert result["shape_stable_r2"] >= 0


def test_shape_classifier_identifies_persistent_decline():
    stable = np.linspace(150, 90, 1134)
    recent = np.linspace(90, 88, 126)
    stock = _fake_history(np.concatenate([stable, recent]))

    result = fixes.analyze_price_shape(stock, 88)

    assert result["shape"] == "gradual_decline"
    assert result["stable_drift_pct"] <= -25
