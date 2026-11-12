"""Audit and replay the original 32-stock sample in a Research notebook."""

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
# Public financial statements available before the June 2022 signal.
TRAILING_FCF = {"AMRC": -594_723_000, "MRTN": -12_362_000, "SEM": -19_986_000, "MSA": 135_821_000}
SPECIALIST_ISSUERS = {"BAC", "MFC", "NBHC", "WABC"}
XEROX_NET_DEBT = 4_271_000_000 - 1_681_000_000
# Use issuer ex-dates where stated. For the other ordinary dividends, use
# the then applicable T+2 rule and require a matching feed ex-date and amount.
STOCK_DIVIDENDS = {
    ("BAC", "70858", "2022-09-01"): ("2022-09-30", .22, "SEC:0000070858-22-000112"),
    ("BAC", "70858", "2022-12-01"): ("2022-12-30", .22, "Bank of America Q4 2022 dividend release"),
    ("BAC", "70858", "2023-03-02"): ("2023-03-31", .22, "Bank of America Q1 2023 dividend release"),
    ("BAC", "70858", "2023-06-01"): ("2023-06-30", .22, "Bank of America Q2 2023 dividend release"),
    ("CTXS", "877890", "2021-09-09"): ("2021-09-24", .37, "SEC:0001193125-21-228138"),
    ("CTXS", "877890", "2021-12-06"): ("2021-12-21", .37, "SEC:0001193125-21-319281"),
    # Gross USD rates published by Manulife, before withholding.
    ("MFC", "1086888", "2022-08-22"): ("2022-09-19", .254433, "Manulife common dividend history (USD)"),
    ("MFC", "1086888", "2022-11-21"): ("2022-12-19", .247515, "Manulife common dividend history (USD)"),
    ("MFC", "1086888", "2023-02-27"): ("2023-03-20", .268008, "Manulife common dividend history (USD)"),
    ("MFC", "1086888", "2023-05-23"): ("2023-06-19", .268521, "Manulife common dividend history (USD)"),
    ("MRTN", "799167", "2022-06-15"): ("2022-06-30", .06, "Marten Transport issuer release 2022-05-04"),
    ("MRTN", "799167", "2022-12-12"): ("2022-12-27", .06, "Marten Transport issuer release 2022-11-30"),
    ("MRTN", "799167", "2023-03-16"): ("2023-03-31", .06, "Marten Transport issuer release 2023-02-20"),
    ("NBHC", "1475841", "2022-08-25"): ("2022-09-15", .23, "National Bank Holdings dividend history"),
    ("NBHC", "1475841", "2022-11-23"): ("2022-12-15", .25, "National Bank Holdings dividend history"),
    ("NBHC", "1475841", "2023-02-23"): ("2023-03-15", .25, "National Bank Holdings dividend history"),
    ("NBHC", "1475841", "2023-05-25"): ("2023-06-15", .26, "National Bank Holdings dividend history"),
    ("SEM", "1320414", "2022-08-15"): ("2022-09-02", .125, "Select Medical FY2022 10-K"),
    ("SEM", "1320414", "2022-11-15"): ("2022-11-29", .125, "Select Medical FY2022 10-K"),
    ("SEM", "1320414", "2023-03-02"): ("2023-03-15", .125, "Select Medical FY2023 10-K"),
    ("SEM", "1320414", "2023-05-17"): ("2023-05-31", .125, "Select Medical FY2023 10-K"),
    ("WABC", "311094", "2022-08-05"): ("2022-08-19", .42, "Westamerica dividend release 2022-07-28"),
    ("WABC", "311094", "2022-11-04"): ("2022-11-18", .42, "Westamerica dividend release 2022-10-27"),
    ("WABC", "311094", "2023-02-03"): ("2023-02-17", .42, "Westamerica dividend release 2023-01-26"),
    ("WABC", "311094", "2023-05-05"): ("2023-05-19", .42, "Westamerica dividend release 2023-04-27"),
    ("XRX", "1770450", "2022-09-29"): ("2022-10-31", .25, "Xerox dividend history"),
    ("XRX", "1770450", "2022-12-29"): ("2023-01-31", .25, "Xerox dividend history"),
    ("XRX", "1770450", "2023-03-30"): ("2023-05-01", .25, "Xerox dividend history"),
    ("XRX", "1770450", "2023-06-29"): ("2023-07-31", .25, "Xerox dividend history"),
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


def cash_available_session(payable, hours):
    next_day = date.fromisoformat(payable) + timedelta(days=1)
    return hours.get_next_market_open(datetime.combine(next_day, time.min), False).date().isoformat()


def reconcile_stock_distributions(actions, ticker, cik, hours, records=STOCK_DIVIDENDS):
    reconciled = []
    counts = Counter()
    for row in actions:
        evidence = records.get((ticker, cik, row["session"])) if row["kind"] == "dividend" else None
        if evidence is not None:
            payable, cash, source = evidence
            if math.isclose(row["cash_per_share"], cash, rel_tol=0, abs_tol=.005001):
                row = dict(row, cash_per_share=cash, pay_session=cash_available_session(payable, hours),
                           source_id=source)
                counts["stock_dividends_reconciled"] += 1
            else:
                counts["stock_dividend_amount_disagreements"] += 1
        reconciled.append(row)
    return reconciled, counts


def cohort_benchmark_actions(pilot, feed_actions, sessions, hours, entry_day, exit_day):
    """Use the US sponsor's complete SPY distribution history for this replay window."""
    if (entry_day, exit_day) != (date(2022, 7, 1), date(2023, 7, 3)):
        raise ValueError("SPY cash records were verified for the June 2022 cohort only")
    sponsor = {day: terms for day, terms in pilot.SPY_DISTRIBUTIONS.items()
               if entry_day < date.fromisoformat(day) <= exit_day}
    if len(sponsor) != 4:
        raise ValueError("Expected all four verified SPY distributions")
    feed = [row for row in feed_actions if row["kind"] == "dividend"
            and entry_day < date.fromisoformat(row["session"]) <= exit_day]
    feed_dates = Counter(row["session"] for row in feed)
    counts = dict(sponsor_distributions=len(sponsor),
                  missing_feed_dates=len(sponsor.keys() - feed_dates.keys()),
                  unexpected_feed_dates=len(feed_dates.keys() - sponsor.keys()),
                  duplicate_feed_rows=sum(count - 1 for count in feed_dates.values()),
                  feed_amount_disagreements=sum(
                      not math.isclose(row["cash_per_share"], sponsor[row["session"]][1],
                                       rel_tol=0, abs_tol=.005001)
                      for row in feed if row["session"] in sponsor))
    actions = [row for row in feed_actions if row["kind"] != "dividend"]
    for day, (payable, amount) in sponsor.items():
        actions.append(dict(security_id=pilot.MARKET, session=day, kind="dividend", cash_per_share=amount,
                            pay_session=cash_available_session(payable, hours),
                            available_at=sessions[date.fromisoformat(day)]["open_at"],
                            source_id=pilot.SPY_DISTRIBUTION_SOURCE))
    return actions, counts


def drawdown_financial_check(ticker, cap, mapped, data, first, config, policy, pilot):
    if ticker == "CTXS":
        return "filing_hold"
    if ticker in SPECIALIST_ISSUERS:
        return "specialist_review_required"
    if ticker == "XRX" and XEROX_NET_DEBT >= cap:
        return "net_debt_at_least_market_cap"
    if (fcf := TRAILING_FCF.get(ticker)) is not None:
        if fcf <= 0:
            return "nonpositive_trailing_free_cash_flow"
        # The shared valuation model caps normalized cash flow at trailing FCF
        # before subtracting its interest buffer. This bound can only rule out.
        valuation = policy["valuation"]
        for case, minimum in (("base", policy["minimum_base_upside_pct"]),
                              ("bull", policy["minimum_bull_upside_pct"])):
            assumptions = valuation[case]
            max_value = fcf * assumptions["fcf_factor"] * assumptions["equity_fcf_multiple"]
            required_value = cap * (1 + valuation["assumed_share_dilution"]) * (1 + minimum / 100)
            if max_value < required_value:
                return "valuation_upper_bound_below_target"
    if not mapped:
        return "financial_evidence_unverified"
    candidates, coverage = pilot.scan_candidates(data, first, config, policy)
    if not candidates or coverage["unverified_quality_inputs"]:
        return "financial_evidence_unverified"
    return "qualified" if candidates[0]["quality"] else "failed_mapped_quality_checks"


REPLAY_ERRORS = (AttributeError, KeyError, TypeError, ValueError, RuntimeError)


def replay_failure(stage, error):
    return {"status": "REPLAY_CHECK_FAILED", "stage": stage, "error_type": type(error).__name__}


def replay_cohort(pilot, data, drawdowns, first, exit_i, config):
    """Compare the verified drawdown cohort and SPY over the same holding window."""
    market_adv = data.adv(pilot.MARKET, first)
    if not market_adv:
        return {"status": "BENCHMARK_INPUT_UNVERIFIED"}
    groups = {
        "drawdown_only": sorted(drawdowns, key=lambda row: (row["drop_pct"], row["sid"])),
        "market": [dict(sid=pilot.MARKET, issuer=pilot.MARKET, adv=market_adv)],
    }
    results = {}
    for strategy, rows in groups.items():
        orders = {first + 1: (first, exit_i, rows)}
        try:
            ledger = pilot.simulate(data, config, first, exit_i + 1, orders, strategy, pilot.HORIZON, 1, 0)
        except REPLAY_ERRORS as error:
            return replay_failure(f"{strategy}_simulation", error)
        trades = ledger["trades"]
        unresolved = sum(not trade["outcome_known"] for trade in trades)
        entry_debit = sum(trade["initial_notional"] + trade["entry_cost"] for trade in trades)
        results[strategy] = dict(ranked=len(rows), fills=len(trades), unresolved=unresolved,
                                 target_hits_at_exit=sum(trade["target_met_at_exit"] is True for trade in trades),
                                 entry_capital_used_pct=round(100 * entry_debit / config["initial_cash"], 4),
                                 net_portfolio_return_pct=None)
        if trades and not unresolved:
            results[strategy]["net_portfolio_return_pct"] = round(
                100 * (ledger["daily"][-1]["nav"] / config["initial_cash"] - 1), 4
            )
    status = ("DEVELOPMENT_REPLAY_ONLY" if all(
        row["net_portfolio_return_pct"] is not None for row in results.values()
    ) else "OUTCOMES_INCOMPLETE")
    return dict(status=status, signal_date=str(pilot.SIGNAL), horizon_days=pilot.HORIZON, strategies=results)


def load_cohort_benchmark(pilot, history, symbol, bar_type, daily, events, sessions, hours):
    stage = "benchmark_raw_bars"
    try:
        bars = pilot.raw_history(history, symbol, bar_type, daily, sessions, pilot.MARKET)
        if {bar["session"] for bar in bars} != {str(day) for day in sessions}:
            return [], [], dict(status="BENCHMARK_INPUT_UNVERIFIED", stage="benchmark_calendar_coverage",
                                bars_received=len(bars), expected_sessions=len(sessions))
        stage = "benchmark_corporate_actions"
        actions, delisted = pilot.market_actions(history, symbol, events, sessions, pilot.MARKET)
        if delisted:
            return [], [], dict(status="BENCHMARK_INPUT_UNVERIFIED", stage="benchmark_delisting_notice")
    except REPLAY_ERRORS as error:
        return [], [], replay_failure(stage, error)
    return bars, actions, None


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
    drawdown_checks = Counter()
    drawdown_outcome_gaps = Counter()
    drawdowns = []
    market_security = dict(security_id=pilot.MARKET, issuer_id=pilot.MARKET, kind="benchmark", currency="USD")
    # Match the standalone pilot: read SPY before subscribing to the individual stocks.
    market_bars, market_actions, benchmark_failure = load_cohort_benchmark(
        pilot, history, market.symbol, bar_type, daily, events, sessions, hours
    )
    replay_inputs = dict(version=1, kind="historical", source="QuantConnect Research development cohort",
                         benchmark_security_id=pilot.MARKET, sessions=list(sessions.values()),
                         securities=[market_security], bars=market_bars, actions=[],
                         membership=[], facts=[])
    filing_facts = pilot.filing_facts()
    for sid in ids:
        row = snapshot[sid]
        ticker = row.symbol.value
        cik = str(getattr(getattr(row, "company_reference", None), "cik", "")).lstrip("0")
        if ticker == "TME" and cik == "1744676":
            counts["documented_ads"] += 1
            continue
        fact = filing_facts.get(ticker, {})
        mapped = fact.get("issuer_id") == cik and fact.get("evidence") is not None
        try:
            book.add_security(row.symbol, daily, fill_forward=False, data_normalization_mode=raw_mode)
            bars = pilot.raw_history(history, row.symbol, bar_type, daily, sessions, sid)
            actions, has_delisting_notice = pilot.market_actions(history, row.symbol, events, sessions, sid)
            actions, dividend_counts = reconcile_stock_distributions(actions, ticker, cik, hours)
            security = dict(security_id=sid, issuer_id=cik or sid, kind="ordinary", currency="USD")
            data = pilot.Dataset(dict(
                version=1, kind="historical", source="QuantConnect Research coverage check",
                benchmark_security_id=pilot.MARKET, sessions=list(sessions.values()),
                securities=[market_security, security],
                bars=bars, actions=actions,
                membership=[dict(security_id=sid, session=str(pilot.SIGNAL), active=True, ticker=ticker,
                                 available_at=sessions[pilot.SIGNAL]["open_at"], source_id="Dated QuantConnect universe")]
                if mapped else [],
                facts=[dict(security_id=sid, **fact)] if mapped else [],
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
        merger_terms_known = has_delisting_notice and ticker == "CTXS" and cik == "877890"
        unknown_delisting = has_delisting_notice and not merger_terms_known
        entry_open_missing = not data.bars[sid].get(first+1, {}).get("open")
        exit_open_missing = not data.bars[sid].get(exit_i, {}).get("open")
        counts["delisting_notices_without_verified_terms"] += int(unknown_delisting)
        counts["next_open_missing"] += int(entry_open_missing)
        counts["horizon_open_missing"] += int(exit_open_missing)
        unknown_dividends = [e for e in data.actions_by_security[sid] if e["kind"] == "dividend" and e["pay"] is None]
        counts["stock_distributions_with_unknown_payment"] += len(unknown_dividends)
        unknown_holding_payments = sum(first+1 < event["i"] <= exit_i for event in unknown_dividends)
        counts["holding_window_distributions_with_unknown_payment"] += unknown_holding_payments
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
            cap = shares * bar["close"]
            if cap < config["min_market_cap"]:
                counts["below_verified_market_cap_floor"] += 1
                continue
            counts["passed_verified_common_floors"] += 1
            prices = data.signal_history(sid, first)
            if len(prices) < 22 or prices["Close"].isna().any():
                counts["drawdown_history_unverified"] += 1
            elif (shock := drawdown_candidate(
                prices, policy, minimum_drop_pct=config["min_drawdown_pct"], now=pilot.SIGNAL
            )) is not None:
                counts["drawdown_signals"] += 1
                drawdowns.append(dict(sid=sid, issuer=cik or sid, adv=adv, drop_pct=shock["drop_recent_peak_pct"]))
                replay_inputs["securities"].append(security)
                replay_inputs["bars"].extend(bars)
                replay_inputs["actions"].extend(actions)
                check = drawdown_financial_check(ticker, cap, mapped, data, first, config, policy, pilot)
                drawdown_checks[check] += 1
                drawdown_outcome_gaps["entry_open_missing"] += int(entry_open_missing)
                drawdown_outcome_gaps["horizon_open_missing"] += int(exit_open_missing)
                drawdown_outcome_gaps["delisting_notice_without_verified_terms"] += int(unknown_delisting)
                drawdown_outcome_gaps["merger_payment_unverified"] += int(merger_terms_known)
                drawdown_outcome_gaps["stocks_with_unknown_dividend_payments"] += int(unknown_holding_payments > 0)
                drawdown_outcome_gaps["unknown_dividend_payments"] += unknown_holding_payments
            if ticker == "CTXS":
                counts["known_filing_hold"] += 1
            elif mapped:
                counts["mapped_quality_inputs"] += 1
            else:
                counts["quality_inputs_unverified"] += 1

    if not drawdowns:
        replay = {"status": "NO_VERIFIED_DRAWDOWNS"}
    elif any(drawdown_outcome_gaps.values()):
        replay = {"status": "DRAWDOWN_OUTCOME_INPUTS_INCOMPLETE"}
    elif benchmark_failure:
        replay = benchmark_failure
    else:
        days = list(sessions)
        stage = "benchmark_sponsor_distributions"
        try:
            actions, benchmark_counts = cohort_benchmark_actions(
                pilot, market_actions, sessions, hours, days[first + 1], days[exit_i]
            )
            replay_inputs["actions"].extend(actions)
            stage = "combined_dataset_validation"
            data = pilot.Dataset(replay_inputs)
        except REPLAY_ERRORS as error:
            replay = replay_failure(stage, error)
        else:
            replay = replay_cohort(pilot, data, drawdowns, first, exit_i, config)
            replay["benchmark_distributions"] = benchmark_counts
    replay["scanner_core_qualified_signals"] = drawdown_checks["qualified"]
    return {"status": "DEVELOPMENT_COVERAGE_ONLY", "sample_size": len(ids), "coverage": dict(counts),
            "drawdown_financial_checks": dict(drawdown_checks), "drawdown_outcome_gaps": dict(drawdown_outcome_gaps),
            "cohort_replay": replay,
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
    cohort_result = run_cohort_audit(_original_notebook_state)
    print(json.dumps(cohort_result.get("cohort_replay", cohort_result), indent=2))
