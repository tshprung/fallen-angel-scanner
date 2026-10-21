"""Yahoo prices are already split adjusted, including with auto_adjust=False."""


def price_history(ticker, *args, **kwargs):
    # Delegate detection of missing/incorrect split adjustments to yfinance's
    # calibrated repair logic. Never apply every split a second time.
    kwargs = dict(kwargs)
    kwargs.setdefault("auto_adjust", False)
    kwargs.setdefault("repair", True)
    history = ticker.history(*args, **kwargs)
    if history is None or history.empty:
        return history
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
