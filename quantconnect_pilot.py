"""Run a bounded development replay with public filing evidence in QuantConnect Research."""

from copy import deepcopy
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import json
import math

from backtest import DEFAULTS
from backtest_data import Dataset
from backtest_engine import ranked_groups, scan_candidates, schedule, simulate
from fundamental_analysis import load_policy


NEW_YORK = ZoneInfo("America/New_York")
WARMUP = datetime(2021, 6, 15)
SIGNAL = date(2022, 6, 30)
END = datetime(2023, 7, 5)
HORIZON = 365
MARKET = "SPY"
# State Street US historical distributions, CUSIP 78462F103. Amounts are in USD.
SPY_DISTRIBUTION_SOURCE = "https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx"
SPY_DISTRIBUTIONS = {
    "2021-06-18": ("2021-07-30", 1.375875),
    "2021-09-17": ("2021-10-29", 1.428117),
    "2021-12-17": ("2022-01-31", 1.636431),
    "2022-03-18": ("2022-04-29", 1.366009),
    "2022-06-17": ("2022-07-29", 1.576871),
    "2022-09-16": ("2022-10-31", 1.596398),
    "2022-12-16": ("2023-01-31", 1.781400),
    "2023-03-17": ("2023-04-28", 1.506204),
    "2023-06-16": ("2023-07-31", 1.638367),
}


def filing_facts():
    # Public SEC filing data, reconciled for the June 2022 development sample.
    # EXLS trailing flows use FY2021 + Q1 2022 - the Q1 2021 comparative.
    period = "2022-03-31"
    evidence = {
        "balance": dict(basis="quarterly", asof=period, values=dict(
            cash=106_540_000, debt=295_374_000, current_debt=35_137_000, equity=700_341_000,
            current_assets=572_618_000, current_liabilities=222_121_000)),
        "cashflow": dict(basis="ttm_quarterly", asof=period, values=dict(ocf=142_312_000, fcf=101_643_000)),
        "income": dict(basis="ttm_quarterly", asof=period, values=dict(
            ebit=158_301_000, interest=5_963_000, ebitda=208_934_000, revenue=1_190_086_000)),
        "annual_fcf": [dict(asof=f"{year}-12-31", fcf=fcf)
                       for year, fcf in [(2021, 147_139_000), (2020, 160_749_000), (2019, 127_876_000)]],
    }
    return {
        "EXLS": dict(issuer_id="1297989", sector="Industrials", industry="Consulting Services",
                     period_end=period, shares_asof="2022-04-26", shares_outstanding=33_286_190,
                     available_at="2022-06-30T20:00:00Z", evidence=evidence,
                     filing_status="METADATA_CHECKED", event_hold=False,
                     source_id="SEC:0001297989-22-000006,0001297989-22-000004,0001104659-22-047905"),
        "MRTN": dict(issuer_id="799167", sector="Industrials", industry="Trucking",
                     period_end=period, shares_asof="2022-04-25", shares_outstanding=81_946_496,
                     available_at="2022-05-06T04:00:00Z", source_id="SEC:0001437749-22-011121"),
        "CTXS": dict(issuer_id="877890", sector="Technology", industry="Software",
                     period_end=period, shares_asof="2022-04-27", shares_outstanding=126_579_926,
                     available_at="2022-05-06T04:00:00Z", filing_status="REVIEW_REQUIRED", event_hold=True,
                     source_id="SEC:0000877890-22-000060,0001193125-22-077283"),
    }


def market_sessions(hours):
    sessions = {}
    cursor = WARMUP
    while cursor < END:
        opening = hours.get_next_market_open(cursor, False)
        if opening >= END:
            break
        closing = hours.get_next_market_close(opening, False)
        if opening < cursor or opening.date() != closing.date() or opening >= closing:
            raise ValueError("Invalid regular exchange session")
        day = opening.date()
        sessions[day] = dict(date=str(day), open_at=opening.replace(tzinfo=NEW_YORK).isoformat(),
                             close_at=closing.replace(tzinfo=NEW_YORK).isoformat())
        cursor = datetime.combine(day + timedelta(days=1), time.min)
    return sessions


def raw_history(history, symbol, bar_type, daily, sessions, sid):
    bars = []
    for bar in history[bar_type](symbol, WARMUP, END, daily):
        day = bar.end_time.date()
        session = sessions.get(day)
        if (not session or bar.time.date() != day or getattr(bar, "is_fill_forward", False)
                or bar.end_time.replace(tzinfo=NEW_YORK).isoformat() != session["close_at"]):
            raise ValueError("Expected a raw bar ending at the regular session close")
        bars.append(dict(security_id=sid, session=str(day), open=float(bar.open),
                         close=float(bar.close), volume=float(bar.volume)))
    return bars


def market_actions(history, symbol, event_types, sessions, sid):
    split_type, split_occurred, dividend_type, delisting_type = event_types
    actions = []
    for event in history[split_type](symbol, WARMUP, END):
        if event.type != split_occurred:
            continue
        day = event.time.date()
        factor = float(event.split_factor)
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("Invalid split factor")
        actions.append(dict(security_id=sid, session=str(day), kind="split", ratio=1/factor,
                            available_at=sessions[day]["open_at"], source_id="QuantConnect split event"))
    split_sessions = {action["session"] for action in actions}
    for event in history[dividend_type](symbol, WARMUP, END):
        day = event.time.date()
        if str(day) in split_sessions:
            raise ValueError("Confirm the distribution share basis for same-session corporate actions")
        amount_paid = float(event.distribution)
        if not math.isfinite(amount_paid) or amount_paid < 0:
            raise ValueError("Invalid cash distribution")
        if amount_paid > 0:
            actions.append(dict(security_id=sid, session=str(day), kind="dividend", cash_per_share=amount_paid,
                                pay_session=None, available_at=sessions[day]["open_at"],
                                source_id="QuantConnect dividend ex-date; payment date unverified"))
    delisted = any(history[delisting_type](symbol, WARMUP, END))
    return actions, delisted


def reconcile_benchmark_distributions(actions, hours):
    dividends = [action for action in actions if action["kind"] == "dividend"]
    if len(dividends) != len(SPY_DISTRIBUTIONS) or {row["session"] for row in dividends} != SPY_DISTRIBUTIONS.keys():
        raise ValueError("SPY ex-dates do not match the issuer distribution history")
    reconciled = []
    amount_disagreements = 0
    for row in actions:
        if row["kind"] != "dividend":
            reconciled.append(row)
            continue
        payable, amount = SPY_DISTRIBUTIONS[row["session"]]
        # The sponsor supplies the amount. Count disagreements beyond ordinary rounding.
        if not math.isclose(row["cash_per_share"], amount, rel_tol=0, abs_tol=0.005001):
            amount_disagreements += 1
        # Without a posting time, cash is available from the next regular open.
        next_day = date.fromisoformat(payable) + timedelta(days=1)
        cash_open = hours.get_next_market_open(datetime.combine(next_day, time.min), False)
        reconciled.append(dict(row, cash_per_share=amount, pay_session=cash_open.date().isoformat(),
                               source_id=SPY_DISTRIBUTION_SOURCE))
    return reconciled, amount_disagreements


def collect_quantconnect_inputs(book, daily, raw_mode, bar_type, event_types):
    book.settings.daily_precise_end_time = True
    book.set_start_date(2023, 7, 6)
    spy = book.add_equity(MARKET, daily, fill_forward=False, data_normalization_mode=raw_mode)
    sessions = market_sessions(spy.exchange.hours)
    universe = book.add_universe(lambda rows: [row.symbol for row in rows])
    cutoff = datetime.combine(SIGNAL, time.min)
    snapshots = list(book.universe_history(universe, cutoff-timedelta(days=1), cutoff).items())
    if len(snapshots) != 1 or snapshots[0][0][1].date() != SIGNAL:
        raise ValueError("Expected the dated universe snapshot at the signal cutoff")

    evidence = filing_facts()
    history = book.history
    bars = raw_history(history, spy.symbol, bar_type, daily, sessions, MARKET)
    if {bar["session"] for bar in bars} != {str(day) for day in sessions}:
        raise ValueError("Benchmark bars do not cover the exchange calendar")
    actions, benchmark_delisted = market_actions(history, spy.symbol, event_types, sessions, MARKET)
    if benchmark_delisted:
        raise ValueError("Unexpected benchmark delisting")
    actions, amount_disagreements = reconcile_benchmark_distributions(actions, spy.exchange.hours)
    benchmark_distributions = sum(row["kind"] == "dividend" for row in actions)
    raw = dict(version=1, kind="historical", source="QuantConnect Cloud and dated public SEC filings",
               benchmark_security_id=MARKET, sessions=list(sessions.values()), bars=bars, actions=actions,
               securities=[dict(security_id=MARKET, issuer_id=MARKET, currency="USD", kind="benchmark")],
               membership=[], facts=[])
    seen = set()
    unmatched_delistings = 0
    for row in snapshots[0][1]:
        ticker = row.symbol.value
        fact = evidence.get(ticker)
        if not fact or str(row.company_reference.cik).lstrip("0") != fact["issuer_id"]:
            continue
        if ticker in seen:
            raise ValueError("Multiple securities matched one audited case")
        seen.add(ticker)
        sid = str(row.symbol.id)
        book.add_security(row.symbol, daily, fill_forward=False, data_normalization_mode=raw_mode)
        stock_bars = raw_history(history, row.symbol, bar_type, daily, sessions, sid)
        events, delisted = market_actions(history, row.symbol, event_types, sessions, sid)
        raw["bars"].extend(stock_bars)
        raw["actions"].extend(events)
        raw["securities"].append(dict(security_id=sid, issuer_id=fact["issuer_id"], currency="USD", kind="ordinary"))
        raw["membership"].append(dict(security_id=sid, session=str(SIGNAL), active=True, ticker=ticker,
                                      available_at=sessions[SIGNAL]["open_at"], source_id="Dated QuantConnect universe"))
        raw["facts"].append(dict(security_id=sid, **{key: value for key, value in fact.items() if key != "issuer_id"}))
        if ticker == "CTXS":
            # September 29 was the last trade. The completed deal was disclosed separately.
            raw["actions"].append(dict(security_id=sid, session="2022-09-30", kind="merger",
                                       cash_per_share=104, pay_session=None, available_at="2022-10-04T04:00:00Z",
                                       source_id="SEC:0001193125-22-256805; Nasdaq ECA2022-262"))
        elif delisted:
            unmatched_delistings += 1
    return raw, dict(public_filing_cases=len(evidence), matched_cases=len(seen),
                     unmatched_delistings=unmatched_delistings,
                     benchmark_distributions_reconciled=benchmark_distributions,
                     benchmark_amount_disagreements=amount_disagreements,
                     unverified_payment_dates=sum(row.get("pay_session", "") is None for row in raw["actions"]))


def replay_development(data, input_counts, policy):
    config = deepcopy(DEFAULTS)
    first, _, eligible = schedule(data, SIGNAL, END.date()-timedelta(days=1), HORIZON,
                                  config["signal_interval_sessions"])
    if len(eligible) != 1 or first not in eligible:
        raise ValueError("Expected one historical signal with its full 365-day calendar")
    candidates, coverage = scan_candidates(data, first, config, policy)
    ranks = ranked_groups(candidates, config)
    market_adv = data.adv(data.benchmark, first)
    if not market_adv:
        raise ValueError("Benchmark lacks usable trailing dollar volume")
    ranks["market"] = [dict(sid=data.benchmark, issuer=data.benchmark, adv=market_adv)]
    exit_session = eligible[first]
    entry_stats = {}
    for strategy, rows in ranks.items():
        orders = {first+1: (first, exit_session, rows)}
        ledger = simulate(data, config, first, exit_session+1, orders, strategy, HORIZON, 1, 0)
        entry_stats[strategy] = dict(ranked=len(rows), fills=len(ledger["trades"]),
                                     unresolved=sum(not trade["outcome_known"] for trade in ledger["trades"]))
    # Exercise the confirmed merger separately from candidate ranking.
    merger_cases = 0
    for sid, security in data.securities.items():
        if security["issuer_id"] != "877890":
            continue
        adv = data.adv(sid, first)
        if not adv:
            continue
        orders = {first+1: (first, exit_session, [dict(sid=sid, issuer="877890", adv=adv)])}
        ledger = simulate(data, config, first, exit_session+1, orders, "scanner_core", HORIZON, 1, 0)
        merger_cases += sum(trade["terminal_events"] == ["merger"] and not trade["outcome_known"]
                            for trade in ledger["trades"])
    # Use a count-only report for this intentionally small case set.
    return dict(status="DEVELOPMENT_ONLY", signal_date=str(SIGNAL), horizon_days=HORIZON,
                input_counts=input_counts, coverage=dict(coverage), strategies=entry_stats,
                merger_cases_with_unverified_settlement=merger_cases,
                performance_gate="INSUFFICIENT_EVIDENCE",
                reasons=["Three purpose-selected filing cases and one signal date",
                         "Settlement dates and full financial evidence require further verification"])


def run_quantconnect_pilot():
    try:
        from AlgorithmImports import DataNormalizationMode, Delisting, Dividend, Resolution, Split, SplitType, TradeBar
        from QuantConnect.Research import QuantBook
    except ImportError:
        return dict(status="QUANTCONNECT_RESEARCH_REQUIRED")

    events = (Split, SplitType.SPLIT_OCCURRED, Dividend, Delisting)
    try:
        raw, counts = collect_quantconnect_inputs(QuantBook(), Resolution.DAILY, DataNormalizationMode.RAW, TradeBar, events)
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
        # Keep vendor values out of notebook output, including exception details.
        return dict(status="INPUT_CHECK_FAILED", stage="QuantConnect data mapping", error_type=type(error).__name__)
    try:
        return replay_development(Dataset(raw), counts, load_policy())
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        return dict(status="INPUT_CHECK_FAILED", stage="Replay input validation", error_type=type(error).__name__)


if __name__ == "__main__":
    print(json.dumps(run_quantconnect_pilot(), indent=2, sort_keys=True))
