"""Yahoo prices are already split adjusted, including with auto_adjust=False."""

import numpy as np
import pandas as pd


def validate_price_bars(history):
    """Reject contradictory candles; never repair them by inventing prices."""
    columns = ["Open", "High", "Low", "Close"]
    if not all(column in history for column in columns):
        return  # Close-only inputs are validated by their individual consumers.
    bars = history[columns].apply(pd.to_numeric, errors="coerce")
    complete = bars.notna().all(axis=1)
    tolerance = bars.abs().max(axis=1).clip(lower=1) * 1e-6
    invalid = complete & (
        ~np.isfinite(bars).all(axis=1)
        | (bars["Low"] > bars["High"] + tolerance)
        | (bars["Close"] < bars["Low"] - tolerance)
        | (bars["Close"] > bars["High"] + tolerance)
        | (bars["Open"] < bars["Low"] - tolerance)
        | (bars["Open"] > bars["High"] + tolerance))
    if invalid.any():
        raise ValueError("Price history contains inconsistent OHLC bounds; source review required")


def price_history(ticker, *args, **kwargs):
    # Delegate detection of missing/incorrect split adjustments to yfinance's
    # calibrated repair logic. Never apply every split a second time.
    kwargs = dict(kwargs)
    kwargs.setdefault("auto_adjust", False)
    kwargs.setdefault("repair", True)
    history = ticker.history(*args, **kwargs)
    if history is None or history.empty:
        return history
    validate_price_bars(history)
    if str(getattr(ticker, "ticker", "")).endswith("=X"):
        return history
    info = getattr(ticker, "info", None)
    if isinstance(info, dict) and info.get("currency") in ("GBp", "GBX", "ILA", "ILa"):
        from scanner_currency import CurrencyUnavailable, quote_unit
        major, scale = quote_unit(info["currency"])
        metadata = ticker.history_metadata
        actual = metadata.get("currency")
        if actual == major:
            # repair=True standardizes GBp/ILA to GBP/ILS. Restore quote
            # units so current prices, targets and liquidity use one scale.
            history = history.copy()
            for column in ("Open", "High", "Low", "Close", "Adj Close", "Dividends", "Capital Gains"):
                if column in history:
                    history[column] /= scale
        elif actual != info["currency"]:
            raise CurrencyUnavailable("Unable to reconcile repaired history currency")
    return history
