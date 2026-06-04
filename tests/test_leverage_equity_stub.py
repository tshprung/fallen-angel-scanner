"""Tests for net debt / Debt-EBITDA and equity-stub leverage gate."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("yfinance", MagicMock())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fallen_angel_scanner import (
    calculate_risk_score,
    get_financial_health,
    should_exclude_for_leverage,
)


class _MockTicker:
    def __init__(self, info, financials=None):
        self.info = info
        self.financials = financials


def _opco_info(**kwargs):
    base = {
        "sector": "Technology",
        "industry": "Software",
        "totalStockholderEquity": 10_000_000_000,
        "debtToEquity": 0.31,
        "totalCurrentAssets": 500_000_000,
        "totalCurrentLiabilities": 200_000_000,
        "totalRevenue": 1_000_000_000,
    }
    base.update(kwargs)
    return base


def _minimal_health(**overrides):
    health = {
        "debt_to_equity": 0.5,
        "current_ratio": 1.55,
        "cash": 0,
        "revenue": 1,
        "market_cap": 1,
        "revenue_growth_yoy": None,
    }
    health.update(overrides)
    return health


def test_equity_stub_excluded():
    info = _opco_info(
        marketCap=2_400_000_000,
        totalDebt=3_100_000_000,
        totalCash=0,
    )
    excl, reason = should_exclude_for_leverage(info)
    assert excl is True
    assert "Equity stub" in reason


def test_equity_stub_threshold_exact():
    info = _opco_info(
        marketCap=2_400_000_000,
        totalDebt=2_400_000_000,
        totalCash=0,
    )
    excl, _ = should_exclude_for_leverage(info)
    assert excl is True


def test_no_stub_when_net_debt_below_mcap():
    info = _opco_info(
        marketCap=2_000_000_000,
        totalDebt=1_000_000_000,
        totalCash=0,
    )
    excl, _ = should_exclude_for_leverage(info)
    assert excl is False


def test_no_stub_when_no_market_cap():
    info = _opco_info(
        marketCap=0,
        totalDebt=3_100_000_000,
        totalCash=0,
    )
    excl, _ = should_exclude_for_leverage(info)
    assert excl is False


def test_debt_ebitda_high_adds_risk():
    health = _minimal_health()
    base = calculate_risk_score(health, "🟡 UNCLEAR", debt_ebitda=6.0)
    without = calculate_risk_score(health, "🟡 UNCLEAR", debt_ebitda=None)
    assert base == without + 2


def test_debt_ebitda_elevated_adds_risk():
    health = _minimal_health(debt_to_equity=0.65, current_ratio=1.4)
    without = calculate_risk_score(health, "🟡 UNCLEAR", debt_ebitda=None)
    with_elev = calculate_risk_score(health, "🟡 UNCLEAR", debt_ebitda=4.0)
    assert with_elev == without + 1


def test_debt_ebitda_low_no_change():
    health = _minimal_health()
    with_deb = calculate_risk_score(health, "🟡 UNCLEAR", debt_ebitda=2.0)
    without = calculate_risk_score(health, "🟡 UNCLEAR", debt_ebitda=None)
    assert with_deb == without


def test_debt_ebitda_none_no_crash():
    health = _minimal_health()
    score = calculate_risk_score(health, "🟡 UNCLEAR", debt_ebitda=None)
    assert 1 <= score <= 10


def test_get_financial_health_returns_net_debt():
    info = _opco_info(totalDebt=5_000_000_000, totalCash=2_000_000_000, marketCap=1e9)
    health = get_financial_health(_MockTicker(info))
    assert health is not None
    assert health["net_debt"] == 3_000_000_000


def test_get_financial_health_returns_debt_ebitda():
    info = _opco_info(
        totalDebt=4_000_000_000,
        totalCash=0,
        ebitda=1_000_000_000,
        marketCap=2e9,
    )
    health = get_financial_health(_MockTicker(info))
    assert health is not None
    assert health["debt_ebitda"] == 4.0
