"""Offline regressions for misleading upside and double split adjustment."""

import pandas as pd
import pytest

from recovery_estimates import estimate_recovery_reference, haircut_recovery_reference
from scanner_history import price_history


class History:
    def __init__(self, values):
        self.frame = pd.DataFrame({"Close": values})
        self.options = None

    def history(self, *args, **kwargs):
        self.options = kwargs
        return self.frame


def test_no_fabricated_fifty_percent_upside_on_missing_data():
    assert estimate_recovery_reference(History([]), {}, 100) == (None, None, None)


def test_bearish_consensus_is_not_discarded():
    low, high, upside = estimate_recovery_reference(
        History([200] * 260), {"targetMeanPrice": 60}, 100
    )
    assert upside == pytest.approx(30)
    assert low == pytest.approx(54)
    assert high == pytest.approx(220)


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf"), None])
def test_invalid_current_price_cannot_produce_target(price):
    assert estimate_recovery_reference(History([200] * 260), {}, price) == (None, None, None)


def test_haircut_does_not_change_midpoint_upside_to_upper_bound():
    low, high, upside = haircut_recovery_reference(180, 220, 100, 100, .85)
    assert (low, high, upside) == pytest.approx((168, 202, 85))


def test_already_split_adjusted_history_is_preserved():
    stock = History([50, 51, 50, 52])
    result = price_history(stock, period="5y")
    assert result["Close"].tolist() == [50, 51, 50, 52]
    assert stock.options == {"period": "5y", "auto_adjust": False, "repair": True}


@pytest.mark.parametrize("row", [
    {"Open": 150, "High": 152.5, "Low": 145, "Close": 138.636364},
    {"Open": 150, "High": 152.5, "Low": 145, "Close": 160},
    {"Open": 155, "High": 152.5, "Low": 145, "Close": 150},
    {"Open": 150, "High": 145, "Low": 152.5, "Close": 150},
])
def test_repaired_or_raw_contradictory_candles_are_source_failures(row):
    stock = History([])
    stock.frame = pd.DataFrame([row])
    original = stock.frame.copy(deep=True)
    with pytest.raises(ValueError, match="inconsistent OHLC"):
        price_history(stock)
    pd.testing.assert_frame_equal(stock.frame, original)


def test_valid_split_adjusted_candles_and_rounding_noise_are_preserved():
    stock = History([])
    stock.frame = pd.DataFrame({"Open": [50, 51], "High": [52, 53],
                               "Low": [49, 50], "Close": [52.000001, 52]})
    pd.testing.assert_frame_equal(price_history(stock), stock.frame)


def test_fx_history_is_validated_before_currency_adapter_early_return():
    stock = History([])
    stock.ticker = "PLNUSD=X"
    stock.frame = pd.DataFrame({"Open": [.25], "High": [.26], "Low": [.24], "Close": [.20]})
    with pytest.raises(ValueError, match="inconsistent OHLC"):
        price_history(stock)


def test_invalid_history_values_do_not_leak_into_estimates():
    _, _, upside = estimate_recovery_reference(
        History([float("inf"), -1, float("nan")]), {"targetMeanPrice": 80}, 100
    )
    assert upside == pytest.approx(-20)
