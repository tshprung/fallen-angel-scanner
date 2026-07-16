import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Match this repo's existing test convention: mock yfinance before import
sys.modules.setdefault("yfinance", MagicMock())

from fallen_angel_scanner import (
    classify_recovery_bucket,
    MIN_RECOVERY_POTENTIAL_PCT,
    MIN_RECOVERY_POTENTIAL_FRESH_CRASH_PCT,
)


def test_high_upside_is_fallen_angel_regardless_of_shape():
    # Clears the main bar -> fallen_angel, even if shape/bottom data is odd
    result = classify_recovery_bucket(
        upside_pct=MIN_RECOVERY_POTENTIAL_PCT + 5,
        price_shape="gradual_decline",
        at_bottom=False,
    )
    assert result == "fallen_angel"


def test_ibm_style_fresh_crash_qualifies():
    # Sudden drop, at/near bottom, upside between the two bars -> fresh_crash
    upside = (MIN_RECOVERY_POTENTIAL_FRESH_CRASH_PCT + MIN_RECOVERY_POTENTIAL_PCT) / 2
    result = classify_recovery_bucket(
        upside_pct=upside, price_shape="sudden_drop", at_bottom=True,
    )
    assert result == "fresh_crash"


def test_sudden_drop_but_not_at_bottom_excluded():
    # Right shape, upside in range, but technicals don't confirm a bottom yet
    upside = (MIN_RECOVERY_POTENTIAL_FRESH_CRASH_PCT + MIN_RECOVERY_POTENTIAL_PCT) / 2
    result = classify_recovery_bucket(
        upside_pct=upside, price_shape="sudden_drop", at_bottom=False,
    )
    assert result is None


def test_gradual_decline_never_qualifies_for_fresh_crash():
    # Right upside range and "at bottom", but wrong shape -> still excluded
    upside = (MIN_RECOVERY_POTENTIAL_FRESH_CRASH_PCT + MIN_RECOVERY_POTENTIAL_PCT) / 2
    result = classify_recovery_bucket(
        upside_pct=upside, price_shape="gradual_decline", at_bottom=True,
    )
    assert result is None


def test_below_fresh_crash_floor_excluded():
    result = classify_recovery_bucket(
        upside_pct=MIN_RECOVERY_POTENTIAL_FRESH_CRASH_PCT - 1,
        price_shape="sudden_drop", at_bottom=True,
    )
    assert result is None


def test_exact_boundary_at_main_bar():
    result = classify_recovery_bucket(
        upside_pct=MIN_RECOVERY_POTENTIAL_PCT,
        price_shape="choppy", at_bottom=False,
    )
    assert result == "fallen_angel"


def test_exact_boundary_at_fresh_crash_floor():
    result = classify_recovery_bucket(
        upside_pct=MIN_RECOVERY_POTENTIAL_FRESH_CRASH_PCT,
        price_shape="sudden_drop", at_bottom=True,
    )
    assert result == "fresh_crash"


def test_choppy_shape_does_not_qualify_for_fresh_crash():
    upside = (MIN_RECOVERY_POTENTIAL_FRESH_CRASH_PCT + MIN_RECOVERY_POTENTIAL_PCT) / 2
    result = classify_recovery_bucket(
        upside_pct=upside, price_shape="choppy", at_bottom=True,
    )
    assert result is None
