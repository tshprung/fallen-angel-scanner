"""Versioned, offline inputs for the US equity research replay."""

from collections import defaultdict
from datetime import date, datetime, timezone
import math

import pandas as pd


ATTESTATIONS = ("dated_membership_includes_failures", "vintage_facts", "raw_unadjusted_bars",
                "exchange_sessions", "corporate_actions_and_terminal_outcomes")
ACTION_KINDS = {"split", "dividend", "capital_gain", "rights_cash", "spin_off",
                "merger", "bankruptcy", "distressed_delisting", "ordinary_delisting"}
TERMINAL = {"merger", "bankruptcy", "distressed_delisting", "ordinary_delisting"}


def instant(value):
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError("Availability and session timestamps require a UTC offset")
    return ts.astimezone(timezone.utc)


def amount(value, minimum=0, optional=False):
    if value is None and optional:
        return None
    if type(value) not in (float, int) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"Expected a finite numeric value >= {minimum}")
    return float(value)


class Dataset:
    """Stable security IDs and calendar-indexed observations; never use ticker as key."""

    def __init__(self, raw):
        if raw["version"] != 1 or raw["kind"] not in {"synthetic", "historical"} or not raw["source"].strip():
            raise ValueError("Expected version 1 dataset with kind and source")
        self.kind, self.source = raw["kind"], raw["source"]
        self.attested = {key: raw.get("attestations", {}).get(key) is True for key in ATTESTATIONS}
        self.benchmark = raw["benchmark_security_id"]
        self.days, self.opens, self.closes = [], [], []
        for row in raw["sessions"]:
            day, op, cl = date.fromisoformat(row["date"]), instant(row["open_at"]), instant(row["close_at"])
            if not op < cl or (self.days and (day <= self.days[-1] or op <= self.closes[-1])):
                raise ValueError("Sessions must be unique, chronological, and nonoverlapping")
            self.days.append(day)
            self.opens.append(op)
            self.closes.append(cl)
        if not self.days:
            raise ValueError("Empty session calendar")
        self.indices = {day: i for i, day in enumerate(self.days)}
        self.securities = {}
        for row in raw["securities"]:
            sid = row["security_id"]
            if (not sid or sid in self.securities or not row["issuer_id"] or row["currency"] != "USD"
                    or row["kind"] not in {"ordinary", "benchmark", "distribution"}):
                raise ValueError("Expected unique USD security IDs and stable issuer IDs")
            self.securities[sid] = row
        if self.securities[self.benchmark]["kind"] != "benchmark":
            raise ValueError("Benchmark must be a distinct tradable total-return proxy")
        self.bars, self.membership, self.facts = defaultdict(dict), defaultdict(list), defaultdict(list)
        self.actions, self.actions_by_security = defaultdict(list), defaultdict(list)
        keys = set()
        for row in raw["bars"]:
            sid, i = self._key(row)
            if i in self.bars[sid]:
                raise ValueError("Duplicate bar for security/session")
            known = instant(row["close_available_at"]) if row.get("close_available_at") else self.closes[i]
            if known < self.closes[i]:
                raise ValueError("Full-session close/volume cannot be known before close")
            self.bars[sid][i] = dict(open=amount(row["open"], 1e-12, True), close=amount(row["close"], 1e-12, True),
                                     volume=amount(row["volume"], 0, True), known=known)
        self.first_bar = {sid: min(rows) for sid, rows in self.bars.items()}
        for row in raw["membership"]:
            sid, i = self._key(row)
            known = instant(row["available_at"])
            key = ("membership", sid, i, known)
            if key in keys or type(row["active"]) is not bool or not row["ticker"] or not row["source_id"]:
                raise ValueError("Invalid or duplicate membership version")
            keys.add(key)
            self.membership[sid].append((i, known, row))
        for row in raw["facts"]:
            sid = row["security_id"]
            if sid not in self.securities:
                raise ValueError("Fact references unknown security")
            period, known = date.fromisoformat(row["period_end"]), instant(row["available_at"])
            shares_asof = date.fromisoformat(row.get("shares_asof", row["period_end"]))
            key = ("fact", sid, period, known)
            if key in keys or period > known.date() or not row["source_id"] or not row["sector"]:
                raise ValueError("Invalid or duplicate statement vintage")
            if not period <= shares_asof <= known.date():
                raise ValueError("Shares date must be on or after the period end and on or before availability")
            keys.add(key)
            amount(row["shares_outstanding"], 1)
            evidence = row.get("evidence")
            if evidence is not None:
                dates = [date.fromisoformat(evidence[name]["asof"]) for name in ("balance", "cashflow", "income")]
                dates.extend(date.fromisoformat(x["asof"]) for x in evidence["annual_fcf"])
                if any(d > period for d in dates):
                    raise ValueError("Statement vintage contains a future financial period")
            self.facts[sid].append((period, known, shares_asof, row))
        for row in raw["actions"]:
            sid, i = self._key(row)
            kind = row["kind"]
            key = ("action", sid, i, kind)
            if kind not in ACTION_KINDS or key in keys or not row["source_id"]:
                raise ValueError("Unknown or duplicate corporate action")
            keys.add(key)
            known = instant(row["available_at"])
            child = row.get("successor_id")
            if child is not None and (child == sid or child not in self.securities):
                raise ValueError("Invalid successor identity")
            ratio = amount(row.get("ratio"), 1e-12, True)
            cash = amount(row.get("cash_per_share"), 0, True)
            if kind == "split" and (ratio is None or child or cash is not None):
                raise ValueError("Split requires only a new/old share ratio")
            if kind == "spin_off" and (not child or ratio is None or cash is not None):
                raise ValueError("Spin-off requires child and shares per parent share")
            if kind in {"dividend", "capital_gain", "rights_cash"} and (cash is None or child or ratio is not None):
                raise ValueError("Cash distribution requires an explicit cash amount")
            if kind in TERMINAL and ((child is None) != (ratio is None)):
                raise ValueError("Terminal stock consideration requires successor and ratio")
            if kind in TERMINAL and child and cash is None:
                raise ValueError("Set cash_per_share explicitly, including zero for stock-only consideration")
            if (kind == "split" or child) and known > self.opens[i]:
                raise ValueError("Share conversions require terms available by the effective session open")
            pay_session = row.get("pay_session", row["session"])
            pay = date.fromisoformat(pay_session) if pay_session is not None else None
            if pay is None and (cash is None or cash <= 0):
                raise ValueError("Unknown payment timing requires an explicit positive cash amount")
            if pay is not None and (pay < self.days[i] or (pay <= self.days[-1] and pay not in self.indices)):
                raise ValueError("Payment date must be an effective session on or after the event")
            event = dict(kind=kind, security_id=sid, i=i, known=known, ratio=ratio,
                         child=child, cash=cash, pay=pay, source_id=row["source_id"])
            self.actions[i].append(event)
            self.actions_by_security[sid].append(event)
        for i, events in self.actions.items():
            terminal_ids = [e["security_id"] for e in events if e["kind"] in TERMINAL]
            if len(terminal_ids) != len(set(terminal_ids)):
                raise ValueError("Multiple terminal events on the same security/session")
            affected = {e["security_id"] for e in events}
            if any(e["child"] in affected for e in events):
                raise ValueError("Consolidate same-session actions on a successor before importing")
            if any(any(j >= i for j in self.bars[sid]) for sid in terminal_ids):
                raise ValueError("Terminal events are effective before open; later old-security bars are inconsistent")
            events.sort(key=lambda e: (e["security_id"], 0 if e["kind"] == "split" else 2 if e["kind"] in TERMINAL else 1, e["kind"]))
        for rows in (*self.membership.values(), *self.facts.values()):
            rows.sort(key=lambda row: row[:2])
        for rows in self.actions_by_security.values():
            rows.sort(key=lambda row: row["i"])

    def _key(self, row):
        sid = row["security_id"]
        if sid not in self.securities:
            raise ValueError("Observation references unknown security")
        return sid, self.indices[date.fromisoformat(row["session"])]

    def member_at(self, sid, i):
        return next((row for effective, known, row in reversed(self.membership[sid])
                     if effective <= i and known <= self.closes[i]), None)

    def facts_at(self, sid, i):
        return next((row for _, known, shares_asof, row in reversed(self.facts[sid])
                     if shares_asof <= self.days[i] and known <= self.closes[i]), None)

    def adv(self, sid, i, window=20):
        """Trailing dollar volume known at signal close (or previous close for exit)."""
        if i + 1 < window:
            return None
        total = 0.
        for j in range(i + 1 - window, i + 1):
            bar = self.bars[sid].get(j)
            if not bar or bar["close"] is None or bar["volume"] is None or bar["known"] > self.closes[i]:
                return None
            total += bar["close"] * bar["volume"]
        return total / window

    def signal_history(self, sid, i):
        """Raw tape normalized using only splits/cash actions known by this cutoff."""
        start = max(0, i - 251)
        # Ignore dates before the first observed listing bar, but never compress
        # a missing session after listing into a shorter lookback.
        first = self.first_bar.get(sid, i + 1)
        start = max(start, first)
        events = defaultdict(list)
        for event in self.actions_by_security[sid]:
            if start <= event["i"] <= i and event["known"] <= self.closes[i]:
                events[event["i"]].append(event)
        rows, split = [], 1.
        for j in range(i, start - 1, -1):
            bar = self.bars[sid].get(j)
            px = bar["close"] if bar and bar["known"] <= self.closes[i] else None
            cash = sum(e["cash"] or 0 for e in events[j]
                       if e["kind"] in {"dividend", "capital_gain", "rights_cash"})
            # Without a sourced per-share adjustment, a spin-off could look
            # like a crash. Leave affected windows unverified.
            if any(e["kind"] in TERMINAL | {"spin_off"} for e in events[j]):
                px = None
            rows.append((self.days[j], px / split if px is not None else None, cash / split))
            for e in events[j]:
                if e["kind"] == "split":
                    split *= e["ratio"]
        if not rows:
            return pd.DataFrame(columns=["Close", "Dividends"])
        days, closes, cash = zip(*reversed(rows))
        return pd.DataFrame({"Close": closes, "Dividends": cash}, index=pd.to_datetime(days), dtype=float)
