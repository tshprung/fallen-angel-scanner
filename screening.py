"""Identify a meaningful decline from a peak within the recent trading window."""

import numpy as np
import pandas as pd
from datetime import datetime, timezone


def drawdown_candidate(history, policy, minimum_drop_pct=20, now=None):
    if history is None or "Close" not in history:
        return None
    today = pd.Timestamp(now or datetime.now(timezone.utc)).date()
    if isinstance(history.index, pd.DatetimeIndex):
        if not history.index.is_unique or not history.index.is_monotonic_increasing:
            return None
        age = (today - history.index[-1].date()).days if len(history.index) else None
        if age is None or not 0 <= age <= 7:
            return None
    close = pd.to_numeric(history["Close"], errors="coerce")
    # Dropping bad rows would change what '21 sessions' means.
    if len(close) < 22 or not (np.isfinite(close.tail(22)) & (close.tail(22) > 0)).all():
        return None
    recent = (float(close.iloc[-1]) / float(close.iloc[-22]) - 1) * 100
    year = close.tail(252)
    if not (np.isfinite(year) & (year > 0)).all():
        return None
    drawdown = (float(close.iloc[-1]) / float(year.max()) - 1) * 100
    window = policy["recent_drawdown_window_sessions"]
    recent_prices = close.tail(window + 1)
    if not (np.isfinite(recent_prices) & (recent_prices > 0)).all():
        return None
    peak = float(recent_prices.max())
    peak_offset = int(np.flatnonzero(recent_prices.to_numpy() == peak)[-1])
    peak_age = len(recent_prices) - 1 - peak_offset
    recent_drawdown = (float(close.iloc[-1]) / peak - 1) * 100
    peak_date = (pd.Timestamp(recent_prices.index[peak_offset]).date().isoformat()
                 if isinstance(recent_prices.index, pd.DatetimeIndex) else None)
    if peak_date and (today - pd.Timestamp(peak_date).date()).days > policy["recent_drawdown_max_calendar_days"]:
        return None
    cohort = None
    if recent <= -minimum_drop_pct:
        cohort = "recent_shock"
    elif recent_drawdown <= -minimum_drop_pct:
        cohort = "recent_drawdown"
    elif (policy["allow_older_drawdowns"] and len(year) >= 200 and drawdown <= policy["sustained_drawdown_pct"]
          and recent >= policy["sustained_max_recent_loss_pct"]):
        cohort = "stabilizing_drawdown"
    if cohort is None:
        return None
    return {"drop_21d_pct": recent, "drop_from_peak_pct": drawdown, "screen_cohort": cohort,
            "drop_recent_peak_pct": recent_drawdown, "recent_peak_age_sessions": peak_age,
            "recent_peak_date": peak_date, "recent_window_sessions": window}
