"""Yahoo prices are already split adjusted, including with auto_adjust=False."""

import numpy as np
import pandas as pd


def distribution_adjusted_close(history):
    """Cash-reinvested series on the latest close's scale; never change quotes."""
    close = pd.to_numeric(history["Close"], errors="coerce")
    cash = pd.Series(0.0, index=close.index)
    for column in ("Dividends", "Capital Gains"):
        if column in history:
            amounts = pd.to_numeric(history[column], errors="coerce")
            if not (np.isfinite(amounts) & (amounts >= 0)).all():
                raise ValueError("Invalid cash-distribution history")
            cash += amounts
    paid = cash > 0
    if paid.any():
        if not (np.isfinite(close[paid]) & (close[paid] > 0)).all():
            raise ValueError("Invalid close on a distribution date")
        # Yahoo's close and cash amounts are on the same split basis.
        growth = pd.Series(1.0, index=close.index)
        growth.loc[paid] += cash[paid] / close[paid]
        return close / growth.shift(-1, fill_value=1).iloc[::-1].cumprod().iloc[::-1]
    if "Adj Close" in history and len(close):
        adjusted = pd.to_numeric(history["Adj Close"], errors="coerce")
        last = adjusted.iloc[-1]
        if np.isfinite(last) and last > 0:
            # A separately adjusted close can cover omitted cash actions.
            return (adjusted / last * close.iloc[-1]).where(np.isfinite(close) & (close > 0))
        raise ValueError("Invalid latest adjusted close")
    return close


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
