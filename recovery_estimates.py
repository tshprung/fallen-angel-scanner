"""Recovery reference levels, not fair value or a 12-month return forecast."""

import math

import pandas as pd


def _positive_finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def _closes(history):
    if history is None or "Close" not in history:
        return pd.Series(dtype=float)
    close = pd.to_numeric(history["Close"], errors="coerce")
    return close[close.map(lambda x: math.isfinite(x) and x > 0)]


def estimate_recovery_reference(stock, info, current_price):
    """Keep contrary evidence and return no estimate when no evidence exists.

    Historical levels are correlated price references, so combine them into
    one input before averaging with the analyst consensus. Bounds describe
    reference dispersion; they are not confidence or bear/bull intervals.
    """
    price = _positive_finite(current_price)
    if price is None:
        return None, None, None
    references = []
    for period, minimum in (("5y", 250), ("1y", 10)):
        try:
            close = _closes(stock.history(period=period))
            if len(close) >= minimum:
                level = (close.mean() + close.quantile(0.8)) / 2 if period == "5y" else close.quantile(0.8)
                references.append(float(level))
        except Exception:
            continue
    inputs = [sum(references) / len(references)] if references else []
    consensus = _positive_finite(info.get("targetMeanPrice"))
    if consensus is not None:
        inputs.append(consensus)
    if not inputs:
        return None, None, None
    midpoint = sum(inputs) / len(inputs)
    return min(inputs) * 0.9, max(inputs) * 1.1, (midpoint / price - 1) * 100


def haircut_recovery_reference(low, high, upside, current_price, haircut):
    """Apply one haircut to all levels, retaining the midpoint upside convention."""
    return (
        current_price + (low - current_price) * haircut,
        current_price + (high - current_price) * haircut,
        upside * haircut,
    )
