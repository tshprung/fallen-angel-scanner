"""Deterministic signal and execution replay. No network, emails, or paper writes."""

from bisect import bisect_left
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, timedelta
import math

from backtest_data import TERMINAL
from fundamental_analysis import assess_solvency, valuation_scenarios
from screening import drawdown_candidate


STRATEGIES = ("scanner_core", "drawdown_only", "value_quality", "matched", "market")
DISTRESS = {"bankruptcy", "distressed_delisting"}


def scan_candidates(data, i, config, policy):
    candidates, coverage = [], Counter()
    for sid, security in sorted(data.securities.items()):
        if security["kind"] != "ordinary":
            continue
        member = data.member_at(sid, i)
        if not member or not member["active"]:
            continue
        coverage["active_members"] += 1
        bar, fact, adv = data.bars[sid].get(i), data.facts_at(sid, i), data.adv(sid, i)
        if not bar or bar["close"] is None or bar["known"] > data.closes[i] or not fact or adv is None:
            coverage["unverified_market_inputs"] += 1
            coverage["input_unverified_members"] += 1
            continue
        today = data.days[i]
        period = date.fromisoformat(fact["period_end"])
        if (today - period).days > policy["fresh_statement_days"]:
            coverage["unverified_market_inputs"] += 1
            coverage["input_unverified_members"] += 1
            continue
        shares = fact["shares_outstanding"]
        for e in data.actions_by_security[sid]:
            if e["kind"] == "split" and period < data.days[e["i"]] <= today and e["known"] <= data.closes[i]:
                shares *= e["ratio"]
        cap = shares * bar["close"]
        if cap < config["min_market_cap"] or adv < config["min_adv"] or bar["close"] < config["min_price"]:
            coverage["below_common_floors"] += 1
            continue
        history = data.signal_history(sid, i)
        price_unverified = len(history) < 22 or history["Close"].isna().any()
        if price_unverified:
            coverage["unverified_drawdown"] += 1
            shock = None
        else:
            shock = drawdown_candidate(history, policy, minimum_drop_pct=config["min_drawdown_pct"], now=today)
        quality = False
        quality_unverified = False
        value = None
        evidence = deepcopy(fact.get("evidence"))
        if fact.get("filing_status") == "REVIEW_REQUIRED" or fact.get("event_hold") is True:
            coverage["archived_event_excluded"] += 1
        elif evidence is not None and fact.get("filing_status") == "METADATA_CHECKED" and fact.get("event_hold") is False:
            for name in ("balance", "cashflow", "income"):
                evidence[name]["age_days"] = (today - date.fromisoformat(evidence[name]["asof"])).days
            info = {"sector": fact["sector"], "industry": fact.get("industry")}
            sol = assess_solvency(evidence, info, policy)
            quality_unverified = sol["status"] == "UNVERIFIED"
            vals = evidence["balance"]["values"]
            if (sol["status"] in {"SCREEN_PASS", "REVIEW"} and vals["equity"] > 0
                    and (vals["debt"] - vals["cash"]) / cap < 1):
                v = valuation_scenarios(evidence, info, bar["close"], cap, 1., policy)
                if v["status"] == "SENSITIVITY":
                    value = v["cases"]["base"]["return_pct"]
                    quality = v["plausible_upside_screen"]
        else:
            quality_unverified = True
        if quality_unverified:
            coverage["unverified_quality_inputs"] += 1
        if price_unverified or quality_unverified:
            coverage["input_unverified_members"] += 1
        candidates.append(dict(sid=sid, issuer=security["issuer_id"], ticker=member["ticker"], sector=fact["sector"],
                               adv=adv, cap=cap, shock=shock, quality=quality, value=value,
                               membership_source_id=member["source_id"], fact_source_id=fact["source_id"],
                               fact_available_at=fact["available_at"]))
    coverage["common_eligible"] = len(candidates)
    return candidates, coverage


def ranked_groups(candidates, config):
    value_order = lambda r: (-r["value"], r["sid"])
    core = sorted((r for r in candidates if r["shock"] and r["quality"]), key=value_order)
    draw = sorted((r for r in candidates if r["shock"]),
                  key=lambda r: (r["shock"]["drop_recent_peak_pct"], r["sid"]))
    value = sorted((r for r in candidates if r["quality"]), key=value_order)
    matched, used = [], set()
    core_issuers = {r["issuer"] for r in core}
    max_distance = math.log(config["match_ratio"])
    # Greedy nearest neighbor in fixed core rank order; no outcome information.
    for r in core:
        neighbors = []
        for m in candidates:
            if m["issuer"] in used | core_issuers or m["sector"] != r["sector"]:
                continue
            size, liquidity = abs(math.log(m["cap"] / r["cap"])), abs(math.log(m["adv"] / r["adv"]))
            if max(size, liquidity) <= max_distance:
                neighbors.append((size + liquidity, m["sid"], m))
        if neighbors:
            match = min(neighbors)[2]
            matched.append({**match, "matched_to": r["sid"]})
            used.add(match["issuer"])
    return {"scanner_core": core, "drawdown_only": draw, "value_quality": value, "matched": matched}


def schedule(data, start, end, horizon, interval):
    """Use only calendar boundaries; purge signals with possible overlapping outcomes."""
    stop = bisect_left(data.days, end + timedelta(days=1))
    first = bisect_left(data.days, start)
    result = {}
    for i in range(first, stop - 1, interval):
        exit_i = bisect_left(data.days, data.days[i+1] + timedelta(days=horizon))
        if exit_i < stop:
            result[i] = exit_i
    return first, stop, result


@dataclass
class Lot:
    record: dict
    units: dict
    exit_i: int
    debit: float
    income: float = 0.
    cash_terms: list = field(default_factory=list)
    touched: bool = False
    path_incomplete: bool = False
    unknown: list = field(default_factory=list)
    terminal: list = field(default_factory=list)


def simulate(data, config, first, stop, orders, strategy, horizon, cost_scale, unknown_recovery):
    cash = config["initial_cash"]
    nav = cash
    lots, trades, daily = [], [], []
    receivable = defaultdict(float)
    last_price = {}
    counts = Counter()
    turnover, costs = 0., 0.
    slots = 1 if strategy == "market" else config["max_positions"]
    target = 2. if horizon == 730 else 1.5

    def fee(notional, adv):
        cfg = config["cost_bps"]
        bps = cfg["commission"] + cfg["half_spread"] + cfg["slippage"] + cfg["impact"] * math.sqrt(notional / adv)
        return notional * cost_scale * bps / 10000.

    def mark(sid, i):
        b = data.bars[sid].get(i)
        return b["close"] if b and b["known"] <= data.closes[i] else None

    def finish(lot, i, proceeds, status):
        trades.append({**lot.record, "exit_session": str(data.days[i]), "exit_status": status,
                       "outcome_known": not lot.unknown, "unknown_reasons": lot.unknown,
                       "terminal_events": lot.terminal, "net_proceeds": proceeds + lot.income,
                       "net_return": (proceeds + lot.income) / lot.debit - 1.,
                       "target_touched_at_close": (lot.touched if not lot.unknown and
                                                   (lot.touched or not lot.path_incomplete) else None),
                       "target_met_at_exit": (proceeds + lot.income) >= target * lot.debit if not lot.unknown else None})

    for i in range(first, stop):
        day = data.days[i]
        traded = defaultdict(float)
        for event in data.actions.get(i, ()):
            sid, kind = event["security_id"], event["kind"]
            # A split also changes the basis of a carried mark.
            if kind == "split" and sid in last_price:
                last_price[sid] /= event["ratio"]
            for lot in lots:
                units = lot.units.get(sid)
                if not units:
                    continue
                if kind == "split":
                    lot.units[sid] *= event["ratio"]
                    continue
                if event["child"]:
                    child = event["child"]
                    lot.units[child] = lot.units.get(child, 0.) + units * event["ratio"]
                if kind in TERMINAL:
                    lot.terminal.append(kind)
                    del lot.units[sid]
                payout = event["cash"]
                known = event["known"]
                if payout is not None and known > data.closes[stop-1]:
                    lot.unknown.append(f"{kind}: cash terms not available inside fold")
                    payout = None
                if kind in TERMINAL and payout is None and not event["child"]:
                    if event["cash"] is None:
                        lot.unknown.append(f"{kind}: terminal proceeds unavailable")
                    payout = last_price.get(sid, 0.) * unknown_recovery
                    known = data.opens[i]  # Explicit scenario mark, not the future proceeds.
                if payout is not None:
                    proceeds = units * payout
                    lot.income += proceeds
                    lot.cash_terms.append((known, proceeds))
                    receivable[(event["pay"], known)] += proceeds
        for pay, known in list(receivable):
            if pay <= day and known <= data.opens[i]:
                cash += receivable.pop((pay, known))
        for lot in list(lots):
            if not lot.units:
                finish(lot, i, 0., "corporate_terminal")
                lots.remove(lot)
            elif i == lot.exit_i:
                proceeds = 0.
                for sid, units in sorted(lot.units.items()):
                    b, adv = data.bars[sid].get(i), data.adv(sid, i-1)
                    opening = b["open"] if b else None
                    gross = units * opening if opening else None
                    if not gross or not adv or gross + traded[sid] > adv * config["participation"]:
                        lot.unknown.append(f"{sid}: planned exit open or capacity unavailable")
                        proceeds += units * last_price.get(sid, 0.) * unknown_recovery
                    else:
                        commission = fee(gross, adv)
                        proceeds += gross - commission
                        turnover += gross
                        costs += commission
                        traded[sid] += gross
                cash += proceeds
                finish(lot, i, proceeds, "scheduled_open" if not lot.unknown else "scenario_exit")
                lots.remove(lot)
        active_issuers = {data.securities[sid]["issuer_id"] for lot in lots for sid in lot.units}
        signal_i, exit_i, ranked = orders.get(i, (None, None, ()))
        for row in ranked:
            if len(lots) >= slots:
                break
            sid = row["sid"]
            if row["issuer"] in active_issuers:
                counts["issuer_already_held"] += 1
                continue
            bar = data.bars[sid].get(i)
            counts["attempted_entries"] += 1
            if not bar or not bar["open"] or any(e["security_id"] == sid and e["kind"] in TERMINAL for e in data.actions.get(i, ())):
                counts["missed_entry_open"] += 1
                continue
            budget = min(cash, nav / slots, row["adv"] * config["participation"] - traded[sid])
            if budget < config["min_order"]:
                counts["insufficient_cash_or_capacity"] += 1
                continue
            gross = budget / (1. + fee(budget, row["adv"]) / budget)
            commission = fee(gross, row["adv"])
            debit = gross + commission
            cash -= debit
            turnover += gross
            costs += commission
            traded[sid] += gross
            active_issuers.add(row["issuer"])
            last_price[sid] = bar["open"]
            lots.append(Lot({**row, "signal_session": str(data.days[signal_i]), "entry_session": str(day),
                             "entry_open": bar["open"], "initial_notional": gross, "entry_cost": commission},
                            {sid: gross / bar["open"]}, exit_i, debit))
            counts["filled_entries"] += 1
        held = {sid for lot in lots for sid in lot.units}
        # Record prior marks for all names with a bar, including newly acquired
        # assets and securities whose current session is missing.
        last_price = {sid: value for sid, value in last_price.items() if sid in held}
        for sid in held:
            price = mark(sid, i)
            if price is not None:
                last_price[sid] = price
        stale = False
        values = []
        for lot in lots:
            value = 0.
            clean = not lot.unknown
            for sid, units in lot.units.items():
                price = mark(sid, i)
                if price is None:
                    stale, clean = True, False
                    lot.path_incomplete = True
                value += units * last_price.get(sid, 0.)
            visible_income = sum(proceeds for known, proceeds in lot.cash_terms if known <= data.closes[i])
            if visible_income < lot.income:
                lot.path_incomplete = True
            if clean and value + visible_income >= target * lot.debit:
                lot.touched = True
            values.append(value)
        recognized = sum(value for (_, known), value in receivable.items() if known <= data.closes[i])
        unrecognized = any(known > data.closes[i] for _, known in receivable)
        nav = cash + recognized + sum(values)
        daily.append(dict(session=str(day), nav=nav, cash=cash, receivable=recognized,
                          positions=len(lots), provisional_mark=stale or unrecognized or any(lot.unknown for lot in lots)))
    if lots:
        raise ValueError("A scheduled position escaped its fold")
    return dict(daily=daily, trades=trades, counts=dict(counts), turnover_notional=turnover, costs=costs)
