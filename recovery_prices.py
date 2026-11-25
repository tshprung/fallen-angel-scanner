"""Daily US market inputs for the recovery watch. All signal windows end at a completed close."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import re

import numpy as np
import pandas as pd
import requests

from ai_research import atomic_json
from scanner_history import distribution_adjusted_close, validate_price_bars

NY = ZoneInfo("America/New_York")
SECTOR_FUNDS = {"Technology": "XLK", "Consumer Cyclical": "XLY", "Healthcare": "XLV",
                "Financial Services": "XLF", "Industrials": "XLI", "Communication Services": "XLC",
                "Basic Materials": "XLB", "Energy": "XLE", "Real Estate": "XLRE",
                "Utilities": "XLU", "Consumer Defensive": "XLP"}

def chart(symbol, params):
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.\-^]{0,14}", symbol):
        raise ValueError("Invalid symbol")
    resp = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/" + symbol,
                        params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=(5, 18))
    resp.raise_for_status()
    item = resp.json()["chart"]["result"][0]
    if item["meta"]["symbol"] != symbol or item["meta"]["currency"] != "USD":
        raise ValueError("Quote identity or currency mismatch")
    return item

def fetch_daily(symbol, end, lookback_days=440):
    def stamp(day):
        return int(datetime.combine(day, time(), timezone.utc).timestamp())
    data = chart(symbol, {"period1": stamp(end - timedelta(days=lookback_days)), "period2": stamp(end+timedelta(days=1)),
                          "interval": "1d", "events": "div,splits,capitalGains"})
    index = pd.to_datetime(data["timestamp"], unit="s", utc=True).tz_convert(NY).tz_localize(None).normalize()
    bars = pd.DataFrame(data["indicators"]["quote"][0], index=index).rename(columns=str.title)
    bars["Adj Close"] = data["indicators"]["adjclose"][0]["adjclose"]
    for field, name in (("dividends","Dividends"), ("capitalGains","Capital Gains")):
        bars[name] = 0.
        for event in data.get("events", {}).get(field, {}).values():
            day = pd.Timestamp(event["date"], unit="s", tz="UTC").tz_convert(NY).tz_localize(None).normalize()
            if day not in bars.index:
                raise ValueError("Distribution without price bar")
            bars.at[day,name] += event["amount"]
    if not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("Invalid daily calendar")
    validate_price_bars(bars)
    return bars

def collect(symbols, end, cache):
    folder = Path(cache) / end.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    def fetch(symbol):
        path = folder / (symbol + ".json")
        try:
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}",symbol):
                raise ValueError("Invalid symbol")
            if not path.exists():
                bars = fetch_daily(symbol, end)
                atomic_json(path, json.loads(bars.to_json(orient="split", date_format="iso")))
            return symbol, None
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
            return symbol, str(exc)[:180]
    with ThreadPoolExecutor(max_workers=6) as pool:
        gaps = {s:e for s,e in pool.map(fetch, sorted(set(symbols))) if e}
    return folder, gaps

def read_bars(folder, symbol):
    d = json.loads((folder/(symbol+".json")).read_text())
    return pd.DataFrame(d["data"], columns=d["columns"], index=pd.to_datetime(d["index"]))


def historical_reference(bars, calendar, event):
    """Compare 60 completed month ends before the pre-drop peak, on one adjusted basis."""
    peak = pd.Timestamp(event["peak_day"])
    adjusted = distribution_adjusted_close(bars.loc[:peak])
    if peak not in adjusted or not np.isfinite(adjusted.at[peak]) or adjusted.at[peak] <= 0:
        return None
    periods = pd.period_range(end=peak.to_period("M")-1, periods=60, freq="M")
    month_ends = calendar.to_series().groupby(calendar.to_period("M")).max().reindex(periods)
    if month_ends.isna().any():
        return None
    prices = adjusted.reindex(pd.DatetimeIndex(month_ends))
    prices = prices.loc[prices.index >= adjusted.index[0]]
    if prices.empty or not (np.isfinite(prices) & (prices > 0)).all():
        return None
    near = prices.between(.9*adjusted.at[peak], 1.1*adjusted.at[peak])
    blocks = (len(periods)-len(near)+np.arange(len(near)))//12
    return {"months":len(near), "near":int(near.sum()), "years_with_three":int((near.groupby(blocks).sum()>=3).sum())}

def current_quote(symbol, now):
    """Timestamped regular or extended-hours print; refuse a stale historical 'current' price."""
    data = chart(symbol, {"interval":"1m", "range":"1d", "includePrePost":"true"})
    for ts, price in reversed(list(zip(data["timestamp"], data["indicators"]["quote"][0]["close"]))):
        if price and np.isfinite(price) and price > 0 and 0 <= now.timestamp()-ts <= 20*60:
            return {"price":price, "at":datetime.fromtimestamp(ts, timezone.utc).isoformat()}
    return None

def drop_events(bars, calendar, start):
    """A crossing is one episode. Missing sessions cannot create a crossing or reset one."""
    data = bars.reindex(calendar)
    close = distribution_adjusted_close(bars).reindex(calendar)
    previous = close.shift(1).rolling(10, min_periods=10).max()
    losses = close / previous - 1
    rows = []
    for i in np.flatnonzero(((losses <= -.30 + 1e-12) & (losses.shift() > -.30 + 1e-12)).to_numpy()):
        day = calendar[i]
        if day < start:
            continue
        peak_day = close.iloc[i-10:i].iloc[::-1].idxmax()
        prior_year = close.iloc[max(0,i-262):i-10]
        near_reference = None
        if len(prior_year) == 252 and prior_year.notna().all():
            peak = previous.iloc[i]
            near_reference = int(prior_year.between(0.90 * peak, 1.10 * peak).sum())
        raw = float(data.at[day,"Close"])
        # Express the earlier reference in signal-day share/distribution units.
        scale = raw/close.iloc[i]
        rows.append({"day":day.date().isoformat(), "close":raw, "drop":round(100*losses.iloc[i],2),
                     "peak_day":peak_day.date().isoformat(), "reference":float(previous.iloc[i]*scale),
                     "near_reference_sessions":near_reference,
                     "range":([float(prior_year.min()*scale), float(prior_year.max()*scale)]
                              if len(prior_year)==252 and prior_year.notna().all() else None)})
    return rows


def bounce_status(bars, calendar, signal):
    """Describe completed closes since the alert. Never count an intraday print as confirmation."""
    window = calendar[calendar >= pd.Timestamp(signal)]
    prices = distribution_adjusted_close(bars).reindex(window)
    if prices.empty or prices.isna().any():
        return "Post-alert closing history incomplete."
    if len(prices) == 1:
        return "No completed session since the alert."
    last = prices.iloc[-1]
    low = prices.min()
    if last == low:
        return "Latest close is at the post-alert low."
    low_day = prices[prices == low].index[-1]
    since_low = prices.loc[low_day:]
    gain = 100 * (last / low - 1)
    return (f"Latest close is {gain:.1f}% above the {low_day.date()} closing low. "
            + ("At least two consecutive higher closes." if len(since_low) >= 3
               and since_low.iloc[-3] < since_low.iloc[-2] < last else "A sustained rebound is unconfirmed."))
