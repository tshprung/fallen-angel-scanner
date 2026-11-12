"""Run a fixed multi-date development replay in QuantConnect Research."""

from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import json
import math

from backtest import DEFAULTS
from backtest_data import Dataset
from backtest_engine import ranked_groups, scan_candidates, simulate
from fundamental_analysis import load_policy
from quantconnect_cohort import STOCK_DIVIDENDS, cash_available_session, reconcile_stock_distributions
from quantconnect_pilot import MARKET, SPY_DISTRIBUTION_SOURCE, market_actions, market_sessions, raw_history
from screening import drawdown_candidate


BATCH_DATES = tuple(date(year, month, day) for year in range(2020, 2024)
                    for month, day in ((3, 31), (9, 30)))
BATCH_SAMPLE_SIZE = 16
BATCH_SEED = "fallen-angel-development-v1"
BATCH_HORIZON = 365
BATCH_START = datetime(2019, 2, 1)
BATCH_END = datetime(2024, 10, 9)
BATCH_ERRORS = (AttributeError, KeyError, TypeError, ValueError, RuntimeError)
# US listing, CUSIP 78462F103. The sponsor lists four distributions per holding window.
BATCH_SPY = {
    "2020-06-19": ("2020-07-31", 1.366242),
    "2020-09-18": ("2020-10-30", 1.339224),
    "2020-12-18": ("2021-01-29", 1.580000),
    "2021-03-19": ("2021-04-30", 1.277788),
    "2021-06-18": ("2021-07-30", 1.375875),
    "2021-09-17": ("2021-10-29", 1.428117),
    "2021-12-17": ("2022-01-31", 1.636431),
    "2022-03-18": ("2022-04-29", 1.366009),
    "2022-06-17": ("2022-07-29", 1.576871),
    "2022-09-16": ("2022-10-31", 1.596398),
    "2022-12-16": ("2023-01-31", 1.781400),
    "2023-03-17": ("2023-04-28", 1.506204),
    "2023-06-16": ("2023-07-31", 1.638367),
    "2023-09-15": ("2023-10-31", 1.583169),
    "2023-12-15": ("2024-01-31", 1.906073),
    "2024-03-15": ("2024-04-30", 1.594937),
    "2024-06-21": ("2024-07-31", 1.759024),
    "2024-09-20": ("2024-10-31", 1.745531),
}


def batch_sample(rows, day, config):
    """Freeze one listing per dated issuer before retrieving any outcome data."""
    counts = Counter()
    listings = []
    for row in rows:
        counts["snapshot_rows"] += 1
        reference = getattr(row, "security_reference", None)
        cik = str(getattr(getattr(row, "company_reference", None), "cik", "") or "").lstrip("0")
        if not cik.isdigit() or reference is None:
            counts["listing_metadata_unverified"] += 1
            continue
        if (reference.security_type != "ST00000001" or str(reference.currency_id).upper() != "USD"
                or reference.is_depositary_receipt or not reference.is_primary_share):
            counts["outside_listing_scope"] += 1
            continue
        cap = float(row.market_cap or 0)
        if not math.isfinite(cap) or cap <= 0:
            counts["vendor_size_unverified"] += 1
            continue
        if cap < config["min_market_cap"]:
            counts["below_vendor_size_floor"] += 1
            continue
        sid = str(row.symbol.id)
        listings.append((sha256(f"{BATCH_SEED}|{day}|{sid}".encode()).digest(), sid, cik, row.symbol))
    selected = {}
    for _, sid, cik, symbol in sorted(listings, key=lambda item: item[:3]):
        selected.setdefault(cik, (sid, cik, symbol))
    counts["eligible_issuers"] = len(selected)
    sample = list(selected.values())[:BATCH_SAMPLE_SIZE]
    counts["sampled"] = len(sample)
    return sample, counts


def batch_spy_actions(sessions, hours, entry, exit_day):
    distributions = []
    for day, (payable, amount) in BATCH_SPY.items():
        ex_date = date.fromisoformat(day)
        if entry < ex_date <= exit_day:
            distributions.append(dict(security_id=MARKET, session=day, kind="dividend",
                                      cash_per_share=amount, pay_session=cash_available_session(payable, hours),
                                      available_at=sessions[ex_date]["open_at"], source_id=SPY_DISTRIBUTION_SOURCE))
    if len(distributions) != 4:
        raise ValueError("Expected four verified SPY distributions for this holding window")
    return distributions


def batch_book(data, config, first, exit_i, rows, strategy, unknown_delistings):
    orders = {first + 1: (first, exit_i, rows)}
    ledger = simulate(data, config, first, exit_i + 1, orders, strategy, BATCH_HORIZON, 1, 0)
    trades = ledger["trades"]
    resolved = [trade for trade in trades
                if trade["outcome_known"] and trade["sid"] not in unknown_delistings]
    unresolved = len(trades) - len(resolved)
    debit = sum(trade["initial_notional"] + trade["entry_cost"] for trade in trades)
    return dict(ranked=len(rows), fills=len(trades), unresolved=unresolved,
                missed_entry_opens=ledger["counts"].get("missed_entry_open", 0),
                target_touches_at_close=sum(trade["target_touched_at_close"] is True for trade in resolved),
                target_paths_unverified=sum(trade["target_touched_at_close"] is None for trade in resolved),
                target_hits_at_exit=sum(trade["target_met_at_exit"] is True for trade in resolved),
                losses_of_50_pct_or_more=sum(trade["net_return"] <= -.5 for trade in resolved),
                entry_capital_used_pct=round(100 * debit / config["initial_cash"], 6),
                net_portfolio_return_pct=(round(100 * (ledger["daily"][-1]["nav"] / config["initial_cash"] - 1), 4)
                                          if trades and not unresolved else None)), debit


def batch_market_reference(data, config, first, exit_i, market_rows, debit):
    if not market_rows or debit < config["min_order"]:
        return None
    market_config = dict(config, initial_cash=debit)
    report, _ = batch_book(data, market_config, first, exit_i, market_rows, "market", set())
    result = report["net_portfolio_return_pct"]
    if result is None or report["entry_capital_used_pct"] < 99.99:
        return None
    return round(result * debit / config["initial_cash"], 4)


def audit_batch_date(book, api, universe, sessions, market_bars, hours, day, config, policy, evidence):
    daily, bar_type, event_types, raw_mode = api
    days = list(sessions)
    signal_i = days.index(day)
    entry = days[signal_i + 1]
    exit_day = days[bisect_left(days, entry + timedelta(days=BATCH_HORIZON))]
    window_days = days[max(0, signal_i - 251):days.index(exit_day) + 1]
    window = {session: sessions[session] for session in window_days}
    start = datetime.combine(window_days[0], time.min)
    end = datetime.combine(exit_day + timedelta(days=1), time.min)
    cutoff = datetime.combine(day, time.min)
    snapshots = list(book.universe_history(universe, cutoff - timedelta(days=1), cutoff).items())
    if len(snapshots) != 1 or snapshots[0][0][1].date() != day:
        raise ValueError("Expected exactly one dated universe snapshot")
    sample, counts = batch_sample(snapshots[0][1], day, config)
    market_security = dict(security_id=MARKET, issuer_id=MARKET, currency="USD", kind="benchmark")
    spy_bars = [bar for bar in market_bars if str(window_days[0]) <= bar["session"] <= str(exit_day)]
    if {bar["session"] for bar in spy_bars} != {str(session) for session in window}:
        raise ValueError("SPY bars do not cover the replay calendar")
    raw = dict(version=1, kind="historical", source="QuantConnect development batch",
               benchmark_security_id=MARKET, sessions=list(window.values()), securities=[market_security],
               bars=spy_bars, actions=batch_spy_actions(window, hours, entry, exit_day), membership=[], facts=[])
    first, exit_i = window_days.index(day), len(window_days) - 1
    unknown_delistings = set()
    provisional_drawdowns = []
    dividend_records = STOCK_DIVIDENDS | evidence.get("dividends", {})
    for sid, cik, symbol in sample:
        ticker = str(symbol.value)
        fact = evidence.get("facts", {}).get((str(day), ticker, cik))
        try:
            book.add_security(symbol, daily, fill_forward=False, data_normalization_mode=raw_mode)
            bars = raw_history(book.history, symbol, bar_type, daily, window, sid, start, end)
            actions, delisted = market_actions(book.history, symbol, event_types, window, sid, start, end, entry)
            actions, dividend_counts = reconcile_stock_distributions(actions, ticker, cik, hours, dividend_records)
            security = dict(security_id=sid, issuer_id=cik, currency="USD", kind="ordinary")
            member = dict(security_id=sid, session=str(day), active=True, ticker=ticker,
                          available_at=sessions[day]["open_at"], source_id="Dated QuantConnect universe")
            facts = [dict(fact, security_id=sid)] if fact is not None else []
            data = Dataset(dict(raw, securities=[market_security, security], bars=bars, actions=actions,
                                membership=[member], facts=facts))
        except BATCH_ERRORS:
            counts["stock_data_failed"] += 1
            continue
        if delisted:
            unknown_delistings.add(sid)
        counts.update(dividend_counts)
        counts["holding_window_delisting_notices"] += int(delisted)
        raw["securities"].append(security)
        raw["membership"].append(member)
        raw["facts"].extend(facts)
        raw["bars"].extend(bars)
        raw["actions"].extend(actions)
        counts["dated_share_basis_present"] += int(data.facts_at(sid, first) is not None)
        bar, adv = data.bars[sid].get(first), data.adv(sid, first)
        if not bar or bar["close"] is None or adv is None:
            counts["signal_market_inputs_unverified"] += 1
        elif bar["close"] >= config["min_price"] and adv >= config["min_adv"]:
            counts["passed_raw_price_liquidity"] += 1
            prices = data.signal_history(sid, first)
            if len(prices) < 22 or prices["Close"].isna().any():
                counts["drawdown_history_unverified"] += 1
                continue
            shock = drawdown_candidate(prices, policy, minimum_drop_pct=config["min_drawdown_pct"], now=day)
            if shock:
                provisional_drawdowns.append(dict(sid=sid, issuer=cik, adv=adv, shock=shock))
                counts["drawdowns_using_vendor_size"] += 1
                counts["drawdowns_missing_entry_open"] += int(not data.bars[sid].get(first + 1, {}).get("open"))
                counts["drawdowns_missing_exit_open"] += int(not data.bars[sid].get(exit_i, {}).get("open"))
                counts["drawdowns_with_delisting_notices"] += int(delisted)
                counts["drawdowns_with_unverified_dividends"] += int(any(
                    action["kind"] == "dividend" and first + 1 < action["i"] <= exit_i and action["pay"] is None
                    for action in data.actions_by_security[sid]))
    data = Dataset(raw)
    candidates, verification = scan_candidates(data, first, config, policy)
    groups = ranked_groups(candidates, config)
    price_inputs_complete = (len(sample) == BATCH_SAMPLE_SIZE and not counts["stock_data_failed"]
                             and not counts["signal_market_inputs_unverified"]
                             and not counts["drawdown_history_unverified"])
    complete = price_inputs_complete and not verification["input_unverified_members"]
    market_adv = data.adv(MARKET, first)
    market_rows = [dict(sid=MARKET, issuer=MARKET, adv=market_adv)] if market_adv else []
    market, _ = batch_book(data, config, first, exit_i, market_rows, "market", set())
    result = dict(signal_date=str(day), entry_date=str(entry), exit_date=str(exit_day),
                  coverage=dict(counts), scanner_input_coverage=dict(verification), market=market,
                  core_comparison="READY_FOR_DEVELOPMENT_REPLAY" if complete else "INPUT_COVERAGE_INCOMPLETE")
    if complete:
        for strategy in ("scanner_core", "drawdown_only"):
            report, debit = batch_book(data, config, first, exit_i, groups[strategy], strategy, unknown_delistings)
            report["spy_with_same_capital_pct"] = batch_market_reference(data, config, first, exit_i, market_rows, debit)
            result[strategy] = report
    elif price_inputs_complete:
        ranked = sorted(provisional_drawdowns, key=lambda row: (row["shock"]["drop_recent_peak_pct"], row["sid"]))
        report, debit = batch_book(data, config, first, exit_i, ranked, "drawdown_only", unknown_delistings)
        report["spy_with_same_capital_pct"] = batch_market_reference(data, config, first, exit_i, market_rows, debit)
        result["drawdown_only_vendor_size"] = report
    return result


def collect_development_batch(book, api, evidence):
    daily, bar_type, event_types, raw_mode = api
    book.settings.daily_precise_end_time = True
    book.set_start_date(2024, 10, 10)
    market = book.add_equity(MARKET, daily, fill_forward=False, data_normalization_mode=raw_mode)
    hours = market.exchange.hours
    sessions = market_sessions(hours, BATCH_START, BATCH_END)
    bars = raw_history(book.history, market.symbol, bar_type, daily, sessions, MARKET, BATCH_START, BATCH_END)
    # The US sponsor supplies all cash distributions. Preserve the split/delisting safety check.
    actions, delisted = market_actions(book.history, market.symbol, event_types, sessions, MARKET, BATCH_START, BATCH_END)
    if delisted or any(action["kind"] == "split" for action in actions):
        raise ValueError("Unexpected SPY split or delisting")
    universe = book.add_universe(lambda rows: [row.symbol for row in rows])
    config, policy = DEFAULTS, load_policy()
    days = list(sessions)
    results = []
    for month_end in BATCH_DATES:
        day = days[bisect_right(days, month_end) - 1]
        if (day.year, day.month) != (month_end.year, month_end.month):
            results.append(dict(month_end=str(month_end), status="SIGNAL_SESSION_MISSING"))
            continue
        try:
            results.append(audit_batch_date(book, api, universe, sessions, bars, hours, day, config, policy, evidence))
        except BATCH_ERRORS as error:
            results.append(dict(signal_date=str(day), status="DATE_CHECK_FAILED", error_type=type(error).__name__))
    return dict(status="DEVELOPMENT_BATCH_ONLY", horizon_days=BATCH_HORIZON,
                sample_size_per_date=BATCH_SAMPLE_SIZE, dates=results, performance_gate="INSUFFICIENT_EVIDENCE")


def run_development_batch(evidence=None):
    try:
        from AlgorithmImports import DataNormalizationMode, Delisting, Dividend, Resolution, Split, SplitType, TradeBar
        from QuantConnect.Research import QuantBook
    except ImportError:
        return dict(status="QUANTCONNECT_RESEARCH_REQUIRED")
    api = (Resolution.DAILY, TradeBar, (Split, SplitType.SPLIT_OCCURRED, Dividend, Delisting), DataNormalizationMode.RAW)
    try:
        return collect_development_batch(QuantBook(), api, evidence or {})
    except BATCH_ERRORS as error:
        return dict(status="BATCH_SETUP_FAILED", error_type=type(error).__name__)


def batch_summary(result):
    if result["status"] != "DEVELOPMENT_BATCH_ONLY":
        return result
    dates = {}
    for detail in result["dates"]:
        day = detail.get("signal_date") or detail["month_end"]
        if "status" in detail:
            dates[day] = detail["status"] + (" " + detail["error_type"] if "error_type" in detail else "")
            continue
        coverage = detail["coverage"]
        strategies = {}
        for strategy in ("scanner_core", "drawdown_only", "drawdown_only_vendor_size"):
            if strategy in detail:
                row = detail[strategy]
                strategies[strategy] = {key: row[key] for key in (
                    "fills", "unresolved", "target_touches_at_close", "target_hits_at_exit",
                    "net_portfolio_return_pct", "spy_with_same_capital_pct")}
        dates[day] = dict(sampled=coverage.get("sampled", 0),
                          verified_size_inputs=coverage.get("dated_share_basis_present", 0),
                          vendor_size_drawdowns=coverage.get("drawdowns_using_vendor_size", 0),
                          stock_data_failed=coverage.get("stock_data_failed", 0),
                          dividend_gaps=coverage.get("drawdowns_with_unverified_dividends", 0),
                          delisting_notices=coverage.get("drawdowns_with_delisting_notices", 0),
                          spy_return_pct=detail["market"]["net_portfolio_return_pct"],
                          core_comparison=detail["core_comparison"], strategies=strategies)
    return dict(status=result["status"], horizon_days=result["horizon_days"], dates=dates,
                performance_gate=result["performance_gate"])


if __name__ == "__main__":
    batch_result = run_development_batch(globals().get("batch_verified_evidence"))
    print(json.dumps(batch_summary(batch_result), separators=(",", ":")))
