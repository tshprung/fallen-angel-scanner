"""Paste this file into a Research cell after running the original 32-stock sampler."""

if __name__ == "__main__":
    _original_notebook_state = dict(globals())

from collections import Counter
from datetime import date, datetime, time, timedelta
import json
import math


# June 2022 filing reconciliation. Keys are historical tickers; the CIK is
# checked against the dated security before its contemporaneous share count is used.
SHARES = {
    "AMRC": ("1488139", "2022-04-29", 51_808_964),
    "BAC": ("70858", "2022-04-28", 8_056_881_363),
    "CTXS": ("877890", "2022-04-27", 126_579_926),
    "EXLS": ("1297989", "2022-04-26", 33_286_190),
    "MFC": ("1086888", "2022-05-31", 1_918_358_018),
    "MRTN": ("799167", "2022-04-25", 81_946_496),
    "MSA": ("66570", "2022-04-22", 39_335_866),
    "NBHC": ("1475841", "2022-04-29", 30_049_172),
    "SEM": ("1320414", "2022-04-30", 130_627_340),
    "WABC": ("311094", "2022-04-27", 26_885_240),
    "XRX": ("1770450", "2022-04-30", 154_862_456),
}
ANCHORS = SHARES.keys() | {"BOWL", "EGP", "SATS", "TME"}
# Ex-dates use the then applicable Nasdaq rule, one business day before
# the stated record date for these ordinary dividends. The feed must agree.
STOCK_DIVIDENDS = {
    ("CTXS", "877890", "2021-09-09"): ("2021-09-24", .37, "SEC:0001193125-21-228138"),
    ("CTXS", "877890", "2021-12-06"): ("2021-12-21", .37, "SEC:0001193125-21-319281"),
    ("MRTN", "799167", "2022-06-15"): ("2022-06-30", .06, "Marten Transport issuer release 2022-05-04"),
    ("MRTN", "799167", "2022-12-12"): ("2022-12-27", .06, "Marten Transport issuer release 2022-11-30"),
    ("MRTN", "799167", "2023-03-16"): ("2023-03-31", .06, "Marten Transport issuer release 2023-02-20"),
}


def member_id(item):
    if isinstance(item, dict):
        for key in ("security_id", "sid", "symbol"):
            if key in item:
                return member_id(item[key])
        return None
    if isinstance(item, (tuple, list)):
        return next((sid for part in item if (sid := member_id(part)) and " " in sid), None)
    symbol = getattr(item, "symbol", item)
    sid = getattr(symbol, "id", symbol)
    return str(sid) if isinstance(sid, str) or sid is not item else None


def selected_ids(namespace, snapshot):
    """Recover the original sample by stable ID, never by ticker or future returns."""
    explicit = namespace.get("cohort_ids")
    inputs = (explicit,) if explicit is not None else namespace.values()
    matches = set()
    for value in inputs:
        if isinstance(value, dict):
            candidates = (value.keys(), value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            candidates = (value,)
        elif hasattr(value, "columns") and hasattr(value, "index"):
            candidates = [value.index, *(value[k] for k in ("security_id", "sid", "symbol") if k in value.columns)]
        else:
            continue
        for candidate in candidates:
            if len(candidate) != 32:
                continue
            ids = frozenset(member_id(item) for item in candidate)
            if len(ids) == 32 and ids <= snapshot.keys():
                if ANCHORS <= {snapshot[sid].symbol.value for sid in ids}:
                    matches.add(ids)
    return sorted(next(iter(matches))) if len(matches) == 1 else None


def reconcile_stock_distributions(actions, ticker, cik, hours):
    reconciled = []
    counts = Counter()
    for row in actions:
        evidence = STOCK_DIVIDENDS.get((ticker, cik, row["session"])) if row["kind"] == "dividend" else None
        if evidence is not None:
            payable, cash, source = evidence
            if math.isclose(row["cash_per_share"], cash, rel_tol=0, abs_tol=.005001):
                next_day = date.fromisoformat(payable) + timedelta(days=1)
                cash_open = hours.get_next_market_open(datetime.combine(next_day, time.min), False)
                row = dict(row, cash_per_share=cash, pay_session=cash_open.date().isoformat(), source_id=source)
                counts["stock_dividends_reconciled"] += 1
            else:
                counts["stock_dividend_amount_disagreements"] += 1
        reconciled.append(row)
    return reconciled, counts


def cohort_audit(book, daily, raw_mode, bar_type, events, pilot, drawdown_candidate, namespace):
    book.settings.daily_precise_end_time = True
    book.set_start_date(2023, 7, 6)
    market = book.add_equity(pilot.MARKET, daily, fill_forward=False, data_normalization_mode=raw_mode)
    hours = market.exchange.hours
    sessions = pilot.market_sessions(hours)
    universe = book.add_universe(lambda rows: [row.symbol for row in rows])
    cutoff = datetime.combine(pilot.SIGNAL, time.min)
    snapshots = list(book.universe_history(universe, cutoff-timedelta(days=1), cutoff).items())
    if len(snapshots) != 1 or snapshots[0][0][1].date() != pilot.SIGNAL:
        return {"status": "SNAPSHOT_NOT_FOUND"}
    rows = list(snapshots[0][1])
    snapshot = {str(row.symbol.id): row for row in rows}
    if len(rows) != len(snapshot):
        return {"status": "DUPLICATE_SECURITY_IDS"}
    ids = selected_ids(namespace, snapshot)
    if ids is None:
        return {"status": "ORIGINAL_SAMPLE_NOT_IDENTIFIED"}

    config, policy = pilot.DEFAULTS, pilot.load_policy()
    history = book.history
    counts = Counter()
    for sid in ids:
        row = snapshot[sid]
        ticker = row.symbol.value
        cik = str(getattr(getattr(row, "company_reference", None), "cik", "")).lstrip("0")
        if ticker == "TME" and cik == "1744676":
            counts["documented_ads"] += 1
            continue
        try:
            book.add_security(row.symbol, daily, fill_forward=False, data_normalization_mode=raw_mode)
            bars = pilot.raw_history(history, row.symbol, bar_type, daily, sessions, sid)
            actions, has_delisting_notice = pilot.market_actions(history, row.symbol, events, sessions, sid)
            actions, dividend_counts = reconcile_stock_distributions(actions, ticker, cik, hours)
            data = pilot.Dataset(dict(
                version=1, kind="historical", source="QuantConnect Research coverage check",
                benchmark_security_id=pilot.MARKET, sessions=list(sessions.values()),
                securities=[dict(security_id=pilot.MARKET, issuer_id=pilot.MARKET, kind="benchmark", currency="USD"),
                            dict(security_id=sid, issuer_id=cik or sid, kind="ordinary", currency="USD")],
                bars=bars, actions=actions, membership=[], facts=[],
            ))
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
            counts["data_check_failed"] += 1
            continue

        first, _, eligible = pilot.schedule(data, pilot.SIGNAL, pilot.END.date()-timedelta(days=1),
                                             pilot.HORIZON, config["signal_interval_sessions"])
        if first not in eligible:
            return {"status": "CALENDAR_HORIZON_MISSING"}
        exit_i = eligible[first]
        counts.update(dividend_counts)
        counts["securities_with_delisting_notices"] += int(has_delisting_notice)
        counts["delisting_notices_without_verified_terms"] += int(
            has_delisting_notice and not (ticker == "CTXS" and cik == "877890"))
        counts["next_open_missing"] += int(not data.bars[sid].get(first+1, {}).get("open"))
        counts["horizon_open_missing"] += int(not data.bars[sid].get(exit_i, {}).get("open"))
        unknown_dividends = [e for e in data.actions_by_security[sid] if e["kind"] == "dividend" and e["pay"] is None]
        counts["stock_distributions_with_unknown_payment"] += len(unknown_dividends)
        counts["holding_window_distributions_with_unknown_payment"] += sum(
            first+1 < event["i"] <= exit_i for event in unknown_dividends)
        bar, adv = data.bars[sid].get(first), data.adv(sid, first)
        if not bar or adv is None:
            counts["missing_close_or_adv"] += 1
        elif bar["close"] < config["min_price"] or adv < config["min_adv"]:
            counts["below_price_or_adv_floor"] += 1
        elif ticker not in SHARES or cik != SHARES[ticker][0]:
            counts["share_basis_unverified"] += 1
        else:
            _, shares_day, shares = SHARES[ticker]
            for action in data.actions_by_security[sid]:
                if (action["kind"] == "split" and date.fromisoformat(shares_day) < data.days[action["i"]]
                        <= pilot.SIGNAL and action["known"] <= data.closes[first]):
                    shares *= action["ratio"]
            if shares * bar["close"] < config["min_market_cap"]:
                counts["below_verified_market_cap_floor"] += 1
                continue
            counts["passed_verified_common_floors"] += 1
            prices = data.signal_history(sid, first)
            if len(prices) < 22 or prices["Close"].isna().any():
                counts["drawdown_history_unverified"] += 1
            else:
                counts["drawdown_signals"] += int(drawdown_candidate(
                    prices, policy, minimum_drop_pct=config["min_drawdown_pct"], now=pilot.SIGNAL) is not None)
            if ticker == "CTXS":
                counts["known_filing_hold"] += 1
            elif ticker == "EXLS":
                counts["mapped_quality_inputs"] += 1
            else:
                counts["quality_inputs_unverified"] += 1

    return {"status": "DEVELOPMENT_COVERAGE_ONLY", "sample_size": len(ids), "coverage": dict(counts),
            "performance_gate": "INSUFFICIENT_EVIDENCE"}


def run_cohort_audit(namespace):
    try:
        from AlgorithmImports import DataNormalizationMode, Delisting, Dividend, Resolution, Split, SplitType, TradeBar
        from QuantConnect.Research import QuantBook
        import fa_pilot_replay as pilot
        from fa_pilot_inputs import drawdown_candidate
    except ImportError:
        return {"status": "QUANTCONNECT_PILOT_IMPORT_REQUIRED"}
    try:
        return cohort_audit(QuantBook(), Resolution.DAILY, DataNormalizationMode.RAW, TradeBar,
                            (Split, SplitType.SPLIT_OCCURRED, Dividend, Delisting), pilot,
                            drawdown_candidate, namespace)
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
        return {"status": "COHORT_CHECK_FAILED", "error_type": type(error).__name__}


if __name__ == "__main__":
    print(json.dumps(run_cohort_audit(_original_notebook_state), indent=2, sort_keys=True))
