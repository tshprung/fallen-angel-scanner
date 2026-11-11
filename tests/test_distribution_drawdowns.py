from types import SimpleNamespace

import pandas as pd
import pytest

from fundamental_analysis import load_policy
from screening import drawdown_candidate


@pytest.mark.parametrize("column", ["Dividends", "Capital Gains"])
def test_cash_distribution_does_not_create_a_shock(column):
    frame = pd.DataFrame({"Close": [100.] * 63 + [75.], column: [0.] * 63 + [25.]})
    assert drawdown_candidate(frame, load_policy()) is None
    assert frame["Close"].iloc[-1] == 75.


def test_distribution_does_not_hide_a_real_loss_or_change_the_latest_quote():
    from scanner_history import distribution_adjusted_close
    frame = pd.DataFrame({"Close": [100.] * 63 + [50.], "Dividends": [0.] * 63 + [25.]})
    signal = drawdown_candidate(frame, load_policy())
    assert signal["screen_cohort"] == "recent_shock"
    assert signal["drop_21d_pct"] == pytest.approx(-25)
    assert signal["drop_from_peak_pct"] == pytest.approx(-25)
    assert distribution_adjusted_close(frame).iloc[-1] == 50


def test_adjusted_close_can_supply_missing_action_information():
    frame = pd.DataFrame({"Close": [100.] * 63 + [75.], "Adj Close": [75.] * 64})
    assert drawdown_candidate(frame, load_policy()) is None


def test_invalid_action_is_not_silently_counted_as_zero():
    frame = pd.DataFrame({"Close": [100.] * 63 + [75.], "Dividends": [0.] * 63 + [float("nan")]})
    with pytest.raises(ValueError, match="cash-distribution"):
        drawdown_candidate(frame, load_policy())


def test_distribution_is_not_a_sudden_break_in_stage_two_shape():
    from scanner_bugfixes import analyze_price_shape_fixed
    frame = pd.DataFrame({"Close": [100.] * 700 + [70.] * 30, "Dividends": [0.] * 700 + [30.] + [0.] * 29})
    shape = analyze_price_shape_fixed(SimpleNamespace(history=lambda **kwargs: frame), 70.)
    assert shape["shape"] == "choppy"
    assert shape["recent_drop_pct"] == pytest.approx(0)
