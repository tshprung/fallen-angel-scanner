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
from scanner_history import validate_price_bars

LEDGER = "paper_tracking.json"
PERFORMANCE_VERSION = 3
BENCHMARK_VERSION = 1


def benchmark_observation(selection, history):
    """SPY comparison for USD observations, at the stock's exact entry/mark sessions."""
    result = {"method_version": BENCHMARK_VERSION, "status": "UNVERIFIED", "ticker": "SPY"}
    if selection.get("quote_currency") != "USD":
        return dict(result, status="UNSUPPORTED_CURRENCY", reason="No non-USD benchmark or FX conversion configured")
    performance = selection["performance"]
    if performance.get("status") not in {"tracking", "complete_12m"} or performance.get("method_version") != PERFORMANCE_VERSION:
        return dict(result, reason="Usable current-method stock outcome required")
    try:
        entry_day = pd.Timestamp(performance["entry_session"]).date()
        mark_day = pd.Timestamp(performance["mark_session"]).date()
        if history is None or history.empty:
            raise ValueError("Benchmark history missing")
        frame = history.copy()
        frame.index = pd.Index([pd.Timestamp(stamp).date() for stamp in frame.index])
        frame = frame[(frame.index >= entry_day) & (frame.index <= mark_day)].sort_index()
        if (frame.empty or frame.index.has_duplicates or frame.index[0] != entry_day
                or frame.index[-1] != mark_day):
            raise ValueError("Benchmark sessions do not match stock endpoints or are duplicated")
        if any((right-left).days > 10 for left, right in zip(frame.index, frame.index[1:])):
            raise ValueError("Benchmark holding-window gap exceeds ten days")
        closes = pd.to_numeric(frame["Close"], errors="coerce")
        if not closes.map(lambda value: finite(value) is not None and value > 0).all():
            raise ValueError("Benchmark holding-window close invalid")
        validate_price_bars(frame)
        entry = finite(frame.iloc[0]["Open"])
        end = finite(frame.iloc[-1]["Close"])
        stock_return = finite(performance.get("return_local_pct"))
        if entry is None or entry <= 0 or end is None or end <= 0 or stock_return is None:
            raise ValueError("Benchmark or stock return invalid")
        benchmark_return = (end/entry-1)*100
        return dict(result, status="MATCHED", entry_session=str(entry_day), mark_session=str(mark_day),
                    return_pct=benchmark_return, stock_minus_benchmark_pp=stock_return-benchmark_return,
                    return_basis="USD; dividend/split-adjusted SPY open-to-close; stock-matched sessions; before trading costs/taxes")
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return dict(result, reason=str(exc) if isinstance(exc, ValueError) else f"Malformed benchmark history ({type(exc).__name__})")


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
                "filing_review": stock.get("filing_review"),
                "official_filing_check": stock.get("official_filing_check"),
                "filing_content_review": stock.get("filing_content_review"),
                "solvency_status": stock.get("solvency_status"),
                "solvency": stock.get("solvency"),
                "valuation": stock.get("valuation"),
                "goal_fit": stock.get("goal_fit"),
                "price_dislocation": stock.get("price_dislocation"),
                "policy_id": (stock.get("financial_evidence") or {}).get("policy_id"),
                "screen_cohort": stock.get("screen_cohort"),
                "performance": {"status": "pending_next_session"}}
        data["selections"].append(item)
        existing.add(identifier)
    _write(path, data)
    return data


def _assess_selection(selection, history, now=None):
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
    # Only assess the holding window; later bad prices cannot invalidate an
    # already completed observation, and earlier gaps cannot be hidden by a
    # valid entry/exit pair. Ten days is a coarse gap guard, not a calendar audit.
    window = frame.loc[:end_day]
    if window.index.has_duplicates:
        return {"status": "unverified", "reason": "Duplicate session dates in holding window"}
    if any((right - left).days > 10 for left, right in zip(window.index, window.index[1:])):
        return {"status": "unverified", "reason": "Price history gap exceeds ten calendar days within holding window"}
    if "Close" not in window:
        return {"status": "unverified", "reason": "Closing-price series is missing"}
    observed = pd.to_numeric(window["Close"], errors="coerce")
    if not observed.map(lambda value: finite(value) is not None and value > 0).all():
        return {"status": "unverified", "reason": "Missing/invalid closing price within holding window"}
    try:
        validate_price_bars(window)
    except ValueError:
        return {"status": "unverified", "reason": "Inconsistent OHLC bounds within holding window"}
    end = finite(row.get("Close"))
    if end is None or end <= 0:
        return {"status": "unverified", "reason": "Missing/invalid closing price"}
    return {"status": status, "entry_session": str(entry_day), "mark_session": str(end_day),
            "entry_adjusted_open": entry, "mark_adjusted_close": end,
            "return_local_pct": (end / entry - 1) * 100,
            "worst_close_return_pct": (float(observed.min()) / entry - 1) * 100,
            "touched_50pct_at_close": bool((observed >= entry * 1.5).any()),
            "ended_50pct": bool(end >= entry * 1.5) if status == "complete_12m" else None,
            "touched_2x_at_close": bool((observed >= entry * 2).any()),
            "ended_2x": bool(end >= entry * 2) if status == "complete_12m" else None,
            "return_basis": "listing currency; dividend/split-adjusted; before costs and taxes"}


def assess_selection(selection, history, now=None):
    try:
        result = _assess_selection(selection, history, now)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        result = {"status": "unverified", "reason": f"Malformed price history ({type(exc).__name__})"}
    return dict(result, method_version=PERFORMANCE_VERSION)


def _needs_refresh(selection):
    performance = selection["performance"]
    return (performance["status"] != "complete_12m"
            or performance.get("method_version") != PERFORMANCE_VERSION)


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
        if not _needs_refresh(selection):
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
        if _needs_refresh(selection):
            selection["performance"] = assess_selection(selection, histories[selection["ticker"]], now)
    benchmark_pending = []
    for selection in data["selections"]:
        performance = selection["performance"]
        saved = performance.get("benchmark") or {}
        if (performance.get("status") == "complete_12m" and saved.get("status") == "MATCHED"
                and saved.get("method_version") == BENCHMARK_VERSION
                and saved.get("entry_session") == performance.get("entry_session")
                and saved.get("mark_session") == performance.get("mark_session")):
            continue
        if (selection.get("quote_currency") == "USD" and performance.get("status") in {"tracking", "complete_12m"}
                and performance.get("entry_session") and performance.get("mark_session")
                and performance.get("method_version") == PERFORMANCE_VERSION):
            benchmark_pending.append(selection)
        else:
            performance["benchmark"] = benchmark_observation(selection, None)
    if benchmark_pending:
        start = min(row["selected_at"][:10] for row in benchmark_pending)
        try:
            benchmark_history = histories.get("SPY")
            if benchmark_history is None:
                benchmark_history = loader("SPY", start)
        except Exception as exc:
            print(f"Paper benchmark unavailable: {type(exc).__name__}")
            benchmark_history = None
        for selection in benchmark_pending:
            selection["performance"]["benchmark"] = benchmark_observation(selection, benchmark_history)
    data["last_refreshed_at"] = pd.Timestamp(now or datetime.now(timezone.utc)).isoformat()
    _write(path, data)
    return data


def cohort_summary(data):
    """Counts only: repeated daily observations are not independent trials."""
    groups = {}
    for selection in (data or {}).get("selections", []):
        key = (selection.get("policy_id") or "legacy/unknown",
               selection.get("screen_cohort") or "legacy/unknown",
               (selection.get("goal_fit") or {}).get("status") or "legacy/unknown")
        group = groups.setdefault(key, {"policy_id": key[0], "screen_cohort": key[1],
            "research_status": key[2], "observations": 0, "tickers": set(),
            "pending": 0, "tracking": 0, "complete_12m": 0, "unverified": 0,
            "touched_50pct": 0, "ended_50pct": 0, "touched_2x": 0, "ended_2x": 0, "ended_loss": 0,
            "benchmark_verified_complete": 0, "outperformed_benchmark": 0})
        group["observations"] += 1
        group["tickers"].add(selection["ticker"])
        performance = selection["performance"]
        status = performance["status"]
        if status == "pending_next_session":
            group["pending"] += 1
        elif status == "complete_12m" and performance.get("method_version") == PERFORMANCE_VERSION:
            group["complete_12m"] += 1
            group["touched_50pct"] += performance.get("touched_50pct_at_close") is True
            group["ended_50pct"] += performance.get("ended_50pct") is True
            group["touched_2x"] += performance.get("touched_2x_at_close") is True
            group["ended_2x"] += performance.get("ended_2x") is True
            value = finite(performance.get("return_local_pct"))
            group["ended_loss"] += value is not None and value < 0
            benchmark = performance.get("benchmark") or {}
            excess = finite(benchmark.get("stock_minus_benchmark_pp"))
            if benchmark.get("status") == "MATCHED" and benchmark.get("method_version") == BENCHMARK_VERSION and excess is not None:
                group["benchmark_verified_complete"] += 1
                group["outperformed_benchmark"] += excess > 0
        elif status == "tracking" and performance.get("method_version") == PERFORMANCE_VERSION:
            group["tracking"] += 1
        else:
            group["unverified"] += 1
    return [dict(group, tickers=sorted(group["tickers"]), unique_tickers=len(group["tickers"]))
            for _, group in sorted(groups.items())]


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def write_report(data, path="paper_tracking_report.md", summary_path=None):
    selections = data["selections"] if data else []
    groups = cohort_summary(data)
    counts = {}
    for selection in selections:
        status = selection["performance"]["status"]
        counts[status] = counts.get(status, 0) + 1
    lines = ["# Forward paper tracking", "",
             "Hypothetical entries use the next session's opening price. Returns are in the listing currency, dividend/split adjusted, before costs and taxes.",
             "Daily selections can repeat the same stock. These are correlated observations, not independent trades or a portfolio backtest.", "",
             f"Saved selections: {len(selections)}. Completed twelve-month observations under method v{PERFORMANCE_VERSION}: {sum(group['complete_12m'] for group in groups)}.", "",
             "Stored status counts (older methods may need refresh): " + (", ".join(f"{key}: {value}" for key, value in sorted(counts.items())) or "No selections recorded yet."), "",
             "Unverified/stale names remain visible; their missing outcomes must not be interpreted as zero losses. USD observations compare against dividend/split-adjusted SPY at the same entry and mark sessions. Non-USD comparisons remain unsupported; no FX conversion is performed. Excess is a percentage-point difference, not risk-adjusted alpha.", "",
             "Completion requires usable holding-window closes, no duplicate sessions, no observed gap over ten calendar days and consistent supplied OHLC bounds. This coarse guard cannot detect every missing exchange session or verify delisting proceeds. Older completed metrics require refresh under the current method.", "",
             "## Cohorts", "",
             "Groups keep financial policy, price-screen cohort and research status as recorded at selection. Legacy/unknown values remain separate. Counts of +50%, doubled or losing outcomes use current-method completed observations only; unresolved outcomes remain in the total. These counts do not establish a success probability or a bankruptcy/delisting rate.", "",
             "| Policy | Price screen | Research status | Observations | Unique tickers | Pending | Tracking | Unverified/stale/old method | Complete | Touched +50% | Ended +50% | Touched 2x | Ended 2x | Ended below entry |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for group in groups:
        values = [group[key] for key in ("policy_id", "screen_cohort", "research_status", "observations",
            "unique_tickers", "pending", "tracking", "unverified", "complete_12m", "touched_50pct", "ended_50pct", "touched_2x", "ended_2x", "ended_loss")]
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    lines += ["", "## Most recent 20 selections", "",
             "| Selected | Ticker | Status | Local return | Entry session | Mark session | SPY return | Stock minus SPY |",
             "|---|---|---|---:|---|---|---:|---:|"]
    for selection in reversed(selections[-20:]):
        performance = selection["performance"]
        value = performance.get("return_local_pct")
        status = performance["status"]
        if status == "complete_12m" and performance.get("method_version") != PERFORMANCE_VERSION:
            status, value = "unverified (old method)", None
        result = f"{value:+.1f}%" if value is not None else "unverified/pending"
        benchmark = performance.get("benchmark") or {}
        matched = (performance.get("method_version") == PERFORMANCE_VERSION
                   and benchmark.get("method_version") == BENCHMARK_VERSION and benchmark.get("status") == "MATCHED")
        benchmark_return = f"{benchmark['return_pct']:+.1f}%" if matched else benchmark.get("status", "unverified/pending")
        excess = f"{benchmark['stock_minus_benchmark_pp']:+.1f} pp" if matched else "unverified/pending"
        values = [selection['selected_at'][:10], selection['ticker'], status, result,
                  performance.get('entry_session', '—'), performance.get('mark_session', '—'), benchmark_return, excess]
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    if summary_path is not None:
        _write(summary_path, {"method_version": PERFORMANCE_VERSION, "benchmark_method_version": BENCHMARK_VERSION,
            "last_refreshed_at": (data or {}).get("last_refreshed_at"),
            "notice": "Correlated forward observations, not a portfolio backtest or calibrated success rate. Unknown outcomes stay in cohort totals.",
            "cohorts": groups})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=LEDGER)
    parser.add_argument("--report", default="paper_tracking_report.md")
    parser.add_argument("--summary", default="paper_tracking_summary.json")
    args = parser.parse_args()
    result = refresh(args.ledger)
    write_report(result, args.report, args.summary)
    print(f"Paper tracking: {len(result['selections']) if result else 0} saved selections")
