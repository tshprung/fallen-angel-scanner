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


def test_invalid_history_values_do_not_leak_into_estimates():
    _, _, upside = estimate_recovery_reference(
        History([float("inf"), -1, float("nan")]), {"targetMeanPrice": 80}, 100
    )
    assert upside == pytest.approx(-20)
