"""Evaluate documented recovery assumptions separately from generic sensitivities.

Records are reviewed research, not automatically verified facts or forecasts.
Missing evidence always remains a research watch. No return probabilities assigned.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlsplit

from scanner_currency import finite

RISK_TOPICS = ("liquidity_and_maturities_24m", "covenants", "going_concern",
               "listing_and_corporate_actions", "dilution")


def load_recovery_cases(path=None):
    records = json.loads(Path(path or Path(__file__).with_name("recovery_cases.json")).read_text(encoding="utf-8"))
    if not isinstance(records, dict) or any(not isinstance(value, dict) for value in records.values()):
        raise ValueError("Recovery cases must be ticker-keyed research objects")
    return records


def day(value):
    if not isinstance(value, str):
        raise ValueError("Dated evidence required")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def sourced(block, today):
    if not isinstance(block, dict) or not isinstance(block.get("finding"), str) or not block["finding"].strip():
        return False
    sources = block.get("sources")
    if not isinstance(sources, list) or not sources:
        return False
    for source in sources:
        if not isinstance(source, dict):
            return False
        try:
            url = urlsplit(source.get("url", ""))
            if (url.scheme != "https" or not url.hostname or url.username or url.password
                    or day(source.get("published_at")) > today):
                return False
        except (ValueError, TypeError):
            return False
    return True


def assess_recovery_case(stock, record=None, policy=None, now=None):
    from fundamental_analysis import load_policy
    policy = policy or load_policy()
    today = (now or datetime.now(timezone.utc)).date() if not isinstance(now, str) else day(now)
    missing = []
    result = {"version": 1, "status": "RESEARCH_WATCH", "checked_at": today.isoformat(),
              "missing": missing, "cases": {}, "notice": "Documented conditional research assumptions; no guarantee of doubling, survival or continued listing."}
    signal = stock.get("price_dislocation") or {}
    age, fall = finite(signal.get("recent_peak_age_sessions")), finite(signal.get("drop_recent_peak_pct"))
    if age is None or not 0 < age <= policy["recent_drawdown_window_sessions"] or fall is None or fall > -20:
        missing.append("A verified decline of at least 20% from a peak within the recent trading window")
    try:
        if not 0 <= (today - day(signal.get("recent_peak_date"))).days <= policy["recent_drawdown_max_calendar_days"]:
            missing.append("A dated recent price peak within the calendar limit")
    except (ValueError, TypeError):
        missing.append("A dated recent price peak within the calendar limit")
    solvency = stock.get("solvency") or {}
    if solvency.get("status") not in {"SCREEN_PASS", "REVIEW"}:
        missing.append("Dated financial evidence passing all covered hard solvency gates")
    evidence = stock.get("financial_evidence") or {}
    for block, name in (("cashflow", "ocf"), ("cashflow", "fcf"), ("income", "ebit")):
        value = finite(((evidence.get(block) or {}).get("values") or {}).get(name))
        if value is None or value <= 0:
            missing.append(f"Positive current statement {name} for a financially resilient recovery case")
    filing = stock.get("official_filing_check") or {}
    if filing.get("status") != "METADATA_CHECKED" or filing.get("blocks_selection"):
        missing.append("Current official filing checks without unresolved publication/event flags")
    valuation = stock.get("valuation") or {}
    cap, price = finite(stock.get("market_cap_usd")), finite(stock.get("current_price"))
    normalized = finite(valuation.get("normalized_fcf_usd"))
    dilution = finite(valuation.get("assumed_share_dilution"))
    if cap and cap > 0 and normalized and normalized > 0 and dilution is not None and dilution >= 0:
        required_value = 2 * cap * (1 + dilution)
        result["doubling_requirements"] = {
            "target_price": 2 * price if price and price > 0 else None,
            "equity_fcf_multiple_at_unchanged_normalized_fcf": required_value / normalized,
            "required_equity_fcf_usd_by_multiple": {str(multiple): required_value / multiple for multiple in (10, 15, 20)},
            "basis": "Reverse sensitivity using current market cap and the generic model's dilution; not a recovery forecast"}
    if not record:
        missing += ["A sourced cause of the recent decline", "A measurable recovery catalyst and invalidation condition within 12 months",
                    "Current filing-content reviews of liquidity, debt, covenants, going concern, listing status and dilution",
                    "Company-specific bear/base/recovery cash-flow and valuation assumptions"]
        return result
    if (not isinstance(record, dict) or any(not isinstance(record.get(name, {}), dict)
            for name in ("cause", "catalyst", "risk_reviews", "valuation"))
            or not isinstance((record.get("valuation") or {}).get("cases", {}), dict)):
        missing.append("Malformed recovery research record")
        return result
    result["research_record"] = record
    result["record_id"] = sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:12]
    source_cutoff = today
    try:
        reviewed_day = day(record.get("reviewed_at"))
        source_cutoff = min(today, reviewed_day)
        if not 0 <= (today - reviewed_day).days <= policy["max_recovery_review_age_days"]:
            missing.append("Recovery review is stale or future-dated")
        expected = day(record.get("catalyst", {}).get("expected_by"))
        if not 0 < (expected - today).days <= 365:
            missing.append("Catalyst must still be ahead and within 365 days")
        if not 0 < (day(record.get("target_by")) - today).days <= 365 or day(record["target_by"]) < expected:
            missing.append("Recovery valuation must follow the catalyst and fall within 365 days")
    except (ValueError, TypeError):
        missing.append("Valid review, catalyst and target dates")
    evidence = stock.get("financial_evidence") or {}
    actual_periods = {name: (evidence.get(name) or {}).get("asof") for name in ("balance", "cashflow", "income")}
    latest = filing.get("latest_financial_report") or {}
    if (not all(actual_periods.values()) or record.get("statement_periods") != actual_periods
            or not latest.get("accessionNumber") or record.get("filing_accession") != latest["accessionNumber"]):
        missing.append("Recovery case must reference the current statement periods and exact latest filing accession")
    if not sourced(record.get("cause"), source_cutoff):
        missing.append("Sourced explanation of the decline")
    catalyst = record.get("catalyst") or {}
    if (not sourced(catalyst, source_cutoff) or not isinstance(catalyst.get("metric"), str) or not catalyst["metric"].strip()
            or not isinstance(catalyst.get("invalidation"), str) or not catalyst["invalidation"].strip()):
        missing.append("Sourced catalyst with a measurable milestone and invalidation condition")
    for topic in RISK_TOPICS:
        review = (record.get("risk_reviews") or {}).get(topic)
        if not sourced(review, source_cutoff) or review.get("status") != "REVIEWED_NO_UNRESOLVED_CONCERN":
            missing.append(f"Unresolved filing-content review: {topic}")
    assumptions = record.get("valuation") or {}
    if assumptions.get("basis") != "equity_fcf_usd_after_financing" or not sourced(assumptions, source_cutoff):
        missing.append("Sourced company-specific equity cash flow after financing, in USD")
    expected_dilution = finite(assumptions.get("expected_dilution_fraction"))
    if expected_dilution is None or not 0 <= expected_dilution <= 1:
        missing.append("Company-specific dilution assumption between zero and 100%")
    values = []
    for name in ("bear", "base", "recovery"):
        case = (assumptions.get("cases") or {}).get(name) or {}
        if not isinstance(case, dict):
            missing.append(f"Malformed valuation case: {name}")
            continue
        fcf, multiple = finite(case.get("equity_fcf_usd")), finite(case.get("equity_fcf_multiple"))
        if not sourced(case, source_cutoff) or fcf is None or fcf <= 0 or multiple is None or multiple <= 0:
            missing.append(f"Sourced positive cash flow and supported multiple: {name}")
            continue
        value = fcf * multiple
        if finite(value) is None:
            missing.append(f"Finite equity valuation: {name}")
            continue
        values.append(value)
        if cap and cap > 0 and price and price > 0 and expected_dilution is not None and 0 <= expected_dilution <= 1:
            equity_ratio = (value / cap) / (1 + expected_dilution)
            target = price * equity_ratio
            if finite(target) is None or target <= 0:
                missing.append(f"Finite positive target price: {name}")
                continue
            result["cases"][name] = dict(case, price=target, return_pct=(equity_ratio - 1) * 100)
    if cap is None or cap <= 0 or price is None or price <= 0:
        missing.append("Positive current price and USD market cap")
    if len(values) == 3 and values != sorted(values):
        missing.append("Bear/base/recovery equity values must be ordered")
    if len(result["cases"]) == 3:
        if result["cases"]["base"]["return_pct"] < policy["minimum_base_upside_pct"]:
            missing.append("Company-specific base case does not meet the minimum upside")
        if result["cases"]["recovery"]["return_pct"] < 100:
            missing.append("Company-specific recovery case does not support doubling")
    if not missing and len(result["cases"]) == 3:
        result["status"] = "DOCUMENTED_12M_CASE"
    return result


def write_recovery_queue(audit, path):
    lines = ["# Twelve-month recovery research queue", "",
             "Goal: a recent meaningful price fall, financial resilience, and a sourced conditional doubling case within one year.", "",
             "Generic valuation sensitivities and headline keywords do not establish a recovery case. This queue does not recommend purchases.", ""]
    queued = [item for item in audit if item.get("decision") == "selected" and item.get("goal_fit")]
    if not queued:
        lines += ["No candidates reached this research stage in this run.", ""]
    for item in queued:
        fit = item["goal_fit"]
        lines += [f"## {item['ticker']}: {fit['status']}", ""]
        signal = item.get("price_dislocation") or {}
        lines += [f"Recent peak decline: {signal.get('drop_recent_peak_pct')}%; peak age: {signal.get('recent_peak_age_sessions')} trading sessions.", ""]
        requirements = fit.get("doubling_requirements")
        if requirements:
            lines += [f"With unchanged normalized cash flow, doubling would require an equity cash-flow multiple of {requirements['equity_fcf_multiple_at_unchanged_normalized_fcf']:.1f}x, including the generic dilution assumption.", "",
                      "Alternatively, these annual equity cash-flow proxies would support 2x at the specified multiples (USD, not revenue):", ""]
            for multiple, amount in requirements["required_equity_fcf_usd_by_multiple"].items():
                lines.append(f"- {multiple}x: ${amount:,.0f}")
            lines += ["", requirements["basis"], ""]
        lines += ["Evidence still required:", ""] + [f"- {message}" for message in fit["missing"]]
        if not fit["missing"]:
            lines += ["- No missing fields under this research schema; review assumptions and source contents before investing."]
        lines += ["", "Record sourced findings in recovery_cases.json using RECOVERY_CASES.md. Never invent a catalyst or clear bankruptcy/listing concerns because a valuation looks cheap.", ""]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
