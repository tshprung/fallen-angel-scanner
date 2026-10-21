"""Separate recent shocks from older drawdowns that have begun stabilizing."""

import numpy as np
import pandas as pd


def drawdown_candidate(history, policy, minimum_drop_pct=20):
    if history is None or "Close" not in history:
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
    cohort = None
    if recent <= -minimum_drop_pct:
        cohort = "recent_shock"
    elif (len(year) >= 200 and drawdown <= policy["sustained_drawdown_pct"]
          and recent >= policy["sustained_max_recent_loss_pct"]):
        cohort = "stabilizing_drawdown"
    if cohort is None:
        return None
    return {"drop_21d_pct": recent, "drop_from_peak_pct": drawdown, "screen_cohort": cohort}
