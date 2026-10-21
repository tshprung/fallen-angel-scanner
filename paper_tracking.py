"""Forward paper observations. No trades, position sizing, or return promises.

Selections are immutable. Performance uses the next session's adjusted open,
and adjusted closes in the listing currency (including dividend adjustments).
Unavailable histories stay in the ledger as unverified, never disappear.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pandas as pd

from scanner_currency import finite

LEDGER = "paper_tracking.json"


def _write(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def record_selections(stocks, path=LEDGER, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"version": 1, "selections": []}
    existing = {item["id"] for item in data["selections"]}
    for stock in stocks:
        identifier = f"{now.date()}:{stock['ticker']}"
        if identifier in existing:
            continue
        item = {"id": identifier, "selected_at": now.isoformat(),
                "ticker": stock["ticker"], "quote_currency": stock["currency"],
                "selection_price": finite(stock.get("current_price")),
                "bucket": stock.get("bucket"), "risk_score": stock.get("risk_score_raw", stock.get("risk_score")),
                "cause_class": stock.get("cause_class"), "catalyst_status": stock.get("catalyst_status"),
                "reference_upside_pct": finite(stock.get("recovery_potential")),
                "upside_basis": stock.get("target_basis", "historical_reference"),
                "market_cap_usd": finite(stock.get("market_cap_usd")),
                "currency_context": stock.get("currency_context"),
                "financial_evidence": stock.get("financial_evidence"),
                "solvency_status": stock.get("solvency_status"),
                "solvency": stock.get("solvency"),
                "valuation": stock.get("valuation"),
                "policy_id": (stock.get("financial_evidence") or {}).get("policy_id"),
                "screen_cohort": stock.get("screen_cohort"),
                "performance": {"status": "pending_next_session"}}
        data["selections"].append(item)
        existing.add(identifier)
    _write(path, data)
    return data


def assess_selection(selection, history, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    if history is None or history.empty:
        return {"status": "unverified", "reason": "No history; possible provider gap, suspension or delisting"}
    # Preserve exchange-local session dates; UTC conversion can move Asian
    # session labels back a day. Selection-day exclusion is conservative.
    dates = pd.Index([pd.Timestamp(i).date() for i in history.index])
    selected_day = pd.Timestamp(selection["selected_at"]).date()
    frame = history.copy()
    frame.index = dates
    frame = frame[(frame.index > selected_day) & (frame.index < now.date())].sort_index()
    if frame.empty:
        return {"status": "pending_next_session"}
    # Do not silently move entry forward if the first possible session is bad.
    entry_day = frame.index[0]
    entry = finite(frame.iloc[0].get("Open"))
    if entry is None or entry <= 0:
        return {"status": "unverified", "reason": "First next-session open is missing/invalid"}
    # A very delayed first quote can indicate a history gap or suspension.
    if (entry_day - selected_day).days > 10:
        return {"status": "unverified", "reason": "First next-session observation delayed over ten days"}
    maturity = entry_day + pd.Timedelta(days=365)
    mature = frame[frame.index >= maturity]
    if not mature.empty:
        end_day, row = mature.index[0], mature.iloc[0]
        status = "complete_12m"
        if (end_day - maturity).days > 10:
            return {"status": "unverified", "reason": "No observation near the twelve-month exit"}
    else:
        end_day, row = frame.index[-1], frame.iloc[-1]
        status = "tracking"
        if (now.date() - end_day).days > 7:
            status = "stale_unverified"
    end = finite(row.get("Close"))
    if end is None or end <= 0:
        return {"status": "unverified", "reason": "Missing/invalid closing price"}
    observed = pd.to_numeric(frame.loc[:end_day, "Close"], errors="coerce")
    observed = observed[observed.map(lambda v: finite(v) is not None and v > 0)]
    return {"status": status, "entry_session": str(entry_day), "mark_session": str(end_day),
            "entry_adjusted_open": entry, "mark_adjusted_close": end,
            "return_local_pct": (end / entry - 1) * 100,
            "worst_close_return_pct": (float(observed.min()) / entry - 1) * 100,
            "touched_2x_at_close": bool((observed >= entry * 2).any()),
            "ended_2x": bool(end >= entry * 2) if status == "complete_12m" else None,
            "return_basis": "listing currency; dividend/split-adjusted; before costs and taxes"}


def refresh(path=LEDGER, loader=None, now=None):
    path = Path(path)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if loader is None:
        import yfinance as yf
        def loader(ticker, start):
            return yf.Ticker(ticker).history(start=start, auto_adjust=True, repair=True)
    # One history request per ticker, including all its daily cohorts.
    starts = {}
    for selection in data["selections"]:
        if selection["performance"]["status"] == "complete_12m":
            continue
        ticker, day = selection["ticker"], selection["selected_at"][:10]
        starts[ticker] = min(starts.get(ticker, day), day)
    histories = {}
    for ticker, day in starts.items():
        try:
            histories[ticker] = loader(ticker, day)
        except Exception as exc:
            print(f"Paper tracking: {ticker} unavailable: {type(exc).__name__}")
            histories[ticker] = None
    for selection in data["selections"]:
        if selection["performance"]["status"] != "complete_12m":
            selection["performance"] = assess_selection(selection, histories[selection["ticker"]], now)
    data["last_refreshed_at"] = pd.Timestamp(now or datetime.now(timezone.utc)).isoformat()
    _write(path, data)
    return data


def write_report(data, path="paper_tracking_report.md"):
    selections = data["selections"] if data else []
    counts = {}
    for selection in selections:
        status = selection["performance"]["status"]
        counts[status] = counts.get(status, 0) + 1
    lines = ["# Forward paper tracking", "",
             "Hypothetical entries use the next session's opening price. Returns are in the listing currency, dividend/split adjusted, before costs and taxes.",
             "Daily selections can repeat the same stock. These are correlated observations, not independent trades or a portfolio backtest.", "",
             f"Saved selections: {len(selections)}. Completed twelve-month observations: {counts.get('complete_12m', 0)}.", "",
             "Status counts: " + (", ".join(f"{key}: {value}" for key, value in sorted(counts.items())) or "No selections recorded yet."), "",
             "Unverified/stale names remain visible; their missing outcomes must not be interpreted as zero losses. No benchmark excess return or USD return is computed.", "",
             "## Most recent 20 selections", "",
             "| Selected | Ticker | Status | Local return | Entry session | Mark session |",
             "|---|---|---|---:|---|---|"]
    for selection in reversed(selections[-20:]):
        performance = selection["performance"]
        value = performance.get("return_local_pct")
        result = f"{value:+.1f}%" if value is not None else "unverified/pending"
        lines.append(f"| {selection['selected_at'][:10]} | {selection['ticker']} | {performance['status']} | {result} | {performance.get('entry_session', '—')} | {performance.get('mark_session', '—')} |")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=LEDGER)
    parser.add_argument("--report", default="paper_tracking_report.md")
    args = parser.parse_args()
    result = refresh(args.ledger)
    write_report(result, args.report)
    print(f"Paper tracking: {len(result['selections']) if result else 0} saved selections")
