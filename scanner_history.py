"""Yahoo prices are already split adjusted, including with auto_adjust=False."""


def price_history(ticker, *args, **kwargs):
    # Delegate detection of missing/incorrect split adjustments to yfinance's
    # calibrated repair logic. Never apply every split a second time.
    kwargs = dict(kwargs)
    kwargs.setdefault("auto_adjust", False)
    kwargs.setdefault("repair", True)
    return ticker.history(*args, **kwargs)
