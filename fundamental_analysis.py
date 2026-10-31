"""Dated financial evidence, conservative solvency gates and FCF sensitivities.

Thresholds are configurable research choices, not fitted survival probabilities.
All statement amounts stay in financialCurrency until explicit USD conversion.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

import pandas as pd

from scanner_currency import finite

POLICY_PATH = Path(__file__).with_name("research_policy.json")


def load_policy(path=POLICY_PATH):
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    for name in ("fresh_statement_days", "max_annual_statement_days", "minimum_interest_coverage",
                 "minimum_current_debt_coverage", "max_net_debt_ebitda", "max_debt_equity",
                 "minimum_burn_runway_months", "minimum_base_upside_pct", "minimum_bull_upside_pct"):
        if finite(policy.get(name)) is None or policy[name] <= 0:
            raise ValueError(f"Policy {name} must be positive and finite")
    valuation = policy["valuation"]
    if type(policy.get("recent_drawdown_window_sessions")) is not int or not 21 <= policy["recent_drawdown_window_sessions"] <= 126:
        raise ValueError("Recent drawdown window must be 21–126 trading intervals")
    if type(policy.get("allow_older_drawdowns")) is not bool:
        raise ValueError("allow_older_drawdowns must be a boolean")
    if type(policy.get("recent_drawdown_max_calendar_days")) is not int or not 21 <= policy["recent_drawdown_max_calendar_days"] <= 200:
        raise ValueError("Recent decline must have a bounded calendar window")
    if type(policy.get("max_recovery_review_age_days")) is not int or not 1 <= policy["max_recovery_review_age_days"] <= 90:
        raise ValueError("Recovery reviews must expire within 1–90 days")
    if not 0 <= valuation["assumed_share_dilution"] <= 1:
        raise ValueError("Assumed dilution must be between zero and one")
    if type(valuation["minimum_annual_fcf_periods"]) is not int or valuation["minimum_annual_fcf_periods"] < 3:
        raise ValueError("FCF normalization requires at least three annual periods")
    for name in ("bear", "base", "bull"):
        for field in ("fcf_factor", "equity_fcf_multiple"):
            if finite(valuation[name].get(field)) is None or valuation[name][field] <= 0:
                raise ValueError(f"Invalid valuation assumption: {name}.{field}")
    products = [valuation[name]["fcf_factor"] * valuation[name]["equity_fcf_multiple"] for name in ("bear", "base", "bull")]
    if products != sorted(products):
        raise ValueError("Bear/base/bull assumptions must produce ordered values")
    if not -100 < policy["sustained_drawdown_pct"] < 0 or not -100 < policy["sustained_max_recent_loss_pct"] < 0:
        raise ValueError("Drawdown thresholds must be negative percentages above -100")
    policy["id"] = sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()[:12]
    return policy


LABELS = {
    "cash": ("Cash And Cash Equivalents",),
    "debt": ("Total Debt", "Total Debt And Capital Lease Obligation"),
    "current_debt": ("Current Debt And Capital Lease Obligation", "Current Debt"),
    "equity": ("Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"),
    "current_assets": ("Current Assets",),
    "current_liabilities": ("Current Liabilities",),
    "ebit": ("EBIT", "Operating Income"),
    "interest": ("Interest Expense", "Interest Expense Non Operating"),
    "ebitda": ("EBITDA",),
    "revenue": ("Total Revenue",),
    "ocf": ("Operating Cash Flow", "Total Cash From Operating Activities"),
    "capex": ("Capital Expenditure", "Capital Expenditures"),
    "shares": ("Ordinary Shares Number", "Share Issued"),
}


def _date(value):
    try:
        date = pd.Timestamp(value)
        return date.tz_localize(None).normalize() if date.tzinfo else date.normalize()
    except Exception:
        return None


def _frame(stock, name, errors):
    try:
        frame = getattr(stock, name)
        if isinstance(frame, pd.DataFrame):
            return frame
    except Exception as exc:
        errors[name] = type(exc).__name__
    return pd.DataFrame()


def _columns(frame, today):
    columns = []
    for column in frame.columns:
        date = _date(column)
        if date is not None and date <= today:
            columns.append((date, column))
    # Duplicate dates are not independent quarters/years.
    unique = {}
    for date, column in columns:
        unique.setdefault(date, column)
    return sorted(unique.items(), reverse=True)


def _row(frame, metric, columns):
    for label in LABELS[metric]:
        if label not in frame.index:
            continue
        values = [finite(frame.loc[label, column]) for _, column in columns]
        if all(value is not None for value in values):
            return values, label
    return None, None


def _consecutive(columns, minimum_days, maximum_days):
    return all(minimum_days <= (columns[i][0] - columns[i + 1][0]).days <= maximum_days
               for i in range(len(columns) - 1))


def _flow_block(quarterly, annual, metrics, today, policy):
    quarters = _columns(quarterly, today)[:4]
    years = _columns(annual, today)[:1]
    options = []
    if len(quarters) == 4 and _consecutive(quarters, 60, 120):
        options.append((quarterly, quarters, "ttm_quarterly", policy["fresh_statement_days"]))
    if years:
        options.append((annual, years, "annual", policy["max_annual_statement_days"]))
    for frame, columns, basis, maximum_age in options:
        if (today - columns[0][0]).days > maximum_age:
            continue
        values, evidence = {}, {}
        for metric in metrics:
            row, label = _row(frame, metric, columns)
            values[metric] = sum(row) if row is not None else None
            evidence[metric] = label
        # Never sum overlapping quarterly and annual periods or use partial TTM.
        required = ("ocf", "capex") if "ocf" in metrics else ("ebit", "revenue")
        if all(values[name] is not None for name in required):
            return {"basis": basis, "asof": str(columns[0][0].date()),
                    "periods": [str(date.date()) for date, _ in columns],
                    "age_days": (today - columns[0][0]).days, "values": values, "rows": evidence}
    return {"basis": "unavailable", "asof": None, "periods": [], "age_days": None,
            "values": {name: None for name in metrics}, "rows": {}}


def collect_evidence(stock, info, now=None, policy=None):
    policy = policy or load_policy()
    today = _date(now or datetime.now(timezone.utc))
    errors = {}
    balance_q = _frame(stock, "quarterly_balance_sheet", errors)
    balance_a = _frame(stock, "balance_sheet", errors)
    cf_q = _frame(stock, "quarterly_cashflow", errors)
    cf_a = _frame(stock, "cashflow", errors)
    income_q = _frame(stock, "quarterly_income_stmt", errors)
    income_a = _frame(stock, "income_stmt", errors)
    balances = []
    for frame, basis in ((balance_q, "quarterly"), (balance_a, "annual")):
        columns = _columns(frame, today)[:1]
        if columns:
            balances.append((columns[0][0], frame, columns, basis))
    balance = {"basis": "unavailable", "asof": None, "age_days": None, "values": {}, "rows": {}}
    if balances:
        date, frame, columns, basis = max(balances, key=lambda item: item[0])
        balance.update(basis=basis, asof=str(date.date()), age_days=(today - date).days)
        for metric in ("cash", "debt", "current_debt", "equity", "current_assets", "current_liabilities"):
            values, label = _row(frame, metric, columns)
            balance["values"][metric] = values[0] if values is not None else None
            balance["rows"][metric] = label
        # Explicit zero total debt establishes zero current debt. Missing debt
        # is never substituted with zero.
        if balance["values"].get("debt") == 0:
            balance["values"]["current_debt"] = 0.0
            balance["rows"]["current_debt"] = "derived from explicit zero Total Debt"
    cashflow = _flow_block(cf_q, cf_a, ("ocf", "capex"), today, policy)
    income = _flow_block(income_q, income_a, ("ebit", "interest", "ebitda", "revenue"), today, policy)
    if cashflow["values"]["ocf"] is not None and cashflow["values"]["capex"] is not None:
        cashflow["values"]["fcf"] = cashflow["values"]["ocf"] - abs(cashflow["values"]["capex"])
    else:
        cashflow["values"]["fcf"] = None
    annual_fcf = []
    years = _columns(cf_a, today)
    for date, column in years:
        ocf, _ = _row(cf_a, "ocf", [(date, column)])
        capex, _ = _row(cf_a, "capex", [(date, column)])
        if ocf is not None and capex is not None:
            annual_fcf.append({"asof": str(date.date()), "fcf": ocf[0] - abs(capex[0])})
    dilution = None
    balance_years = _columns(balance_a, today)[:2]
    if len(balance_years) == 2 and _consecutive(balance_years, 300, 430):
        shares, _ = _row(balance_a, "shares", balance_years)
        if shares and shares[1] > 0:
            dilution = shares[0] / shares[1] - 1
    return {"financial_currency": info.get("financialCurrency"), "balance": balance,
            "cashflow": cashflow, "income": income, "annual_fcf": annual_fcf,
            "annual_share_growth": dilution, "fetch_errors": errors,
            "source": "Yahoo Finance via yfinance; statement period ends, not filing dates",
            "observed_at": pd.Timestamp(now or datetime.now(timezone.utc)).isoformat(),
            "policy_id": policy["id"], "policy": policy}


def specialist_requirements(info):
    sector = str(info.get("sector") or "").lower()
    industry = str(info.get("industry") or "").lower()
    if "bank" in industry:
        return ["Regulatory capital/CET1 and jurisdictional requirements", "Deposit/funding stability and liquidity", "Credit losses and asset quality"]
    if "insurance" in industry:
        return ["Jurisdiction-specific regulatory solvency/capital", "Reserve adequacy and underwriting results", "Asset/liability duration and liquidity"]
    if "reit" in industry or sector == "real estate":
        return ["FFO/AFFO with issuer reconciliation", "Property/debt maturities, secured debt and occupancy", "Distribution coverage and maintenance capex"]
    if sector == "financial services":
        return ["Business-specific capital, funding, asset quality and regulatory requirements"]
    return []


def assess_solvency(evidence, info, policy=None):
    policy = policy or load_policy()
    specialist = specialist_requirements(info)
    if specialist:
        return {"status": "SPECIALIST_REVIEW", "flags": [], "missing": specialist,
                "review": ["Ordinary-company solvency model does not apply"], "metrics": {}, "policy_id": policy["id"]}
    balance, cf, income = evidence["balance"], evidence["cashflow"], evidence["income"]
    values, flows, earnings = balance["values"], cf["values"], income["values"]
    flags, missing, review, metrics = [], [], [], {}
    if not info.get("sector"):
        missing.append("Sector classification")
    for name, block in (("balance", balance), ("cashflow", cf), ("income", income)):
        if block["age_days"] is None or block["age_days"] > policy["fresh_statement_days"]:
            missing.append(f"Fresh {name} statement (maximum {policy['fresh_statement_days']} days from period end)")
        if name != "balance" and block["basis"] == "annual":
            review.append(f"{name}: annual fallback; current TTM quarters unavailable")
    for name in ("cash", "debt", "current_debt", "equity", "current_assets", "current_liabilities"):
        if values.get(name) is None:
            missing.append(f"Statement {name}")
    for name in ("ocf", "fcf"):
        if flows.get(name) is None:
            missing.append(f"Statement {name}")
    for name in ("ebit", "revenue"):
        if earnings.get(name) is None:
            missing.append(f"Statement {name}")
    for name, value in values.items():
        if name != "equity" and value is not None and value < 0:
            missing.append(f"Invalid negative {name}")
    dates = [_date(block["asof"]) for block in (balance, cf, income) if block["asof"]]
    if dates and (max(dates) - min(dates)).days > 120:
        missing.append("Financial statement dates do not align within 120 days")
    cash, debt, current, equity = (values.get(name) for name in ("cash", "debt", "current_debt", "equity"))
    ocf, fcf = flows.get("ocf"), flows.get("fcf")
    ebit, interest, ebitda = (earnings.get(name) for name in ("ebit", "interest", "ebitda"))
    # CFO classifications differ across accounting standards. Subtract an
    # additional gross-interest buffer even if CFO may already include it.
    # This is deliberately conservative, not a claim of standardized FCFE.
    funding_fcf = fcf - abs(interest) if fcf is not None and interest is not None else fcf if debt == 0 else None
    if funding_fcf is not None:
        metrics["fcf_after_interest_buffer"] = funding_fcf
    if equity is not None and debt is not None:
        if equity <= 0 and debt > 0:
            flags.append("Non-positive book equity with debt")
        elif equity > 0:
            metrics["debt_equity"] = debt / equity
            if debt / equity > policy["max_debt_equity"]:
                flags.append("Statement debt/equity exceeds policy")
        elif debt == 0:
            missing.append("Positive book equity for the ordinary-company ratio model")
    if debt is not None and debt > 0:
        if interest is None or abs(interest) == 0 or ebit is None:
            missing.append("Usable statement interest expense and EBIT for a company with debt")
        else:
            metrics["interest_coverage"] = ebit / abs(interest)
            if metrics["interest_coverage"] < policy["minimum_interest_coverage"]:
                flags.append("Insufficient interest coverage")
        if cash is not None and debt > cash:
            if ebitda is None or ebitda <= 0:
                missing.append("Positive statement EBITDA for net leverage assessment")
            else:
                metrics["net_debt_ebitda"] = (debt - cash) / ebitda
                if metrics["net_debt_ebitda"] > policy["max_net_debt_ebitda"]:
                    flags.append("Net debt/EBITDA exceeds policy")
        review.append("Debt due in months 13–24, covenants and committed facilities require filing review")
    if cash is not None and current is not None and funding_fcf is not None and current > 0:
        metrics["current_debt_coverage"] = (cash + .75 * max(funding_fcf, 0)) / current
        if metrics["current_debt_coverage"] < policy["minimum_current_debt_coverage"]:
            flags.append("Cash plus stressed annual FCF does not cover current debt adequately")
        review.append("Current debt is a balance-sheet proxy, not a complete contractual maturity schedule")
    if cash is not None and funding_fcf is not None and funding_fcf < 0:
        metrics["cash_runway_months"] = 12 * cash / -funding_fcf
        if metrics["cash_runway_months"] < policy["minimum_burn_runway_months"]:
            flags.append("Cash runway under policy minimum at the current FCF burn rate")
        else:
            review.append("Cash burn requires a funded turnaround thesis")
    if ocf is not None and ocf <= 0:
        review.append("Non-positive operating cash flow")
    if ebit is not None and ebit <= 0:
        review.append("Non-positive operating earnings require a turnaround thesis")
    assets, liabilities = values.get("current_assets"), values.get("current_liabilities")
    if assets is not None and liabilities is not None and liabilities > 0:
        metrics["current_ratio"] = assets / liabilities
        if metrics["current_ratio"] < 1:
            review.append("Current assets below current liabilities")
    dilution = evidence.get("annual_share_growth")
    if dilution is not None and dilution > policy["max_annual_share_growth"]:
        review.append("Annual share-count growth exceeds policy; dilution needs review")
    # Screen-pass means only covered checks passed, never guaranteed survival.
    status = "EXCLUDE" if flags else "UNVERIFIED" if missing else "REVIEW" if review else "SCREEN_PASS"
    return {"status": status, "flags": flags, "missing": missing, "review": review,
            "metrics": metrics, "policy_id": policy["id"]}


def valuation_scenarios(evidence, info, current_price, cap_usd, financial_to_usd, policy=None):
    policy = policy or load_policy()
    result = {"status": "UNAVAILABLE", "reason": None, "policy_id": policy["id"], "cases": {}}
    if specialist_requirements(info):
        result["reason"] = "Specialist sector requires a different valuation model"
        return result
    price, cap, fx = finite(current_price), finite(cap_usd), finite(financial_to_usd)
    if any(value is None or value <= 0 for value in (price, cap, fx)):
        result["reason"] = "Invalid price, market cap or financial FX"
        return result
    cf = evidence["cashflow"]
    if cf["age_days"] is None or cf["age_days"] > policy["fresh_statement_days"]:
        result["reason"] = "Cash-flow evidence missing or stale"
        return result
    required = policy["valuation"]["minimum_annual_fcf_periods"]
    years = evidence["annual_fcf"][:required]
    if len(years) < required or not _consecutive([(_date(item["asof"]), None) for item in years], 300, 430):
        result["reason"] = "Insufficient consecutive annual FCF history"
        return result
    if (_date(cf["asof"]) - _date(years[0]["asof"])).days > 450:
        result["reason"] = "Annual FCF normalization history too old"
        return result
    current_fcf = finite(cf["values"].get("fcf"))
    if current_fcf is None or current_fcf <= 0 or any(item["fcf"] <= 0 for item in years):
        result["reason"] = "Positive current FCF and positive annual normalization history required"
        return result
    debt = evidence["balance"]["values"].get("debt")
    interest = evidence["income"]["values"].get("interest")
    if debt is None or (debt > 0 and interest is None):
        result["reason"] = "Debt or gross interest evidence missing for the financing buffer"
        return result
    buffer = abs(interest) if interest is not None else 0
    normalized = (min(current_fcf, median(item["fcf"] for item in years)) - buffer) * fx
    if normalized <= 0:
        result["reason"] = "No positive normalized cash flow after the additional interest buffer"
        return result
    assumptions = policy["valuation"]
    for name in ("bear", "base", "bull"):
        case = assumptions[name]
        # This is an equity cash-flow proxy after the financing buffer.
        # Do not also subtract net debt as for enterprise-value multiples.
        equity_value = normalized * case["fcf_factor"] * case["equity_fcf_multiple"]
        target = price * equity_value / (cap * (1 + assumptions["assumed_share_dilution"]))
        if finite(target) is None or target <= 0:
            result.update(reason="Non-finite or invalid scenario arithmetic", cases={})
            return result
        result["cases"][name] = {"price": target, "return_pct": (target / price - 1) * 100,
                                  "fcf_factor": case["fcf_factor"], "equity_fcf_multiple": case["equity_fcf_multiple"]}
    result.update(status="SENSITIVITY", normalized_fcf_usd=normalized,
                  additional_interest_buffer_usd=buffer * fx,
                  assumed_share_dilution=assumptions["assumed_share_dilution"],
                  normalization_periods=years, basis=cf["basis"],
                  description=assumptions["description"],
                  bull_2x=result["cases"]["bull"]["return_pct"] >= 100,
                  minimum_bull_upside_pct=policy["minimum_bull_upside_pct"],
                  bull_meets_upside_goal=result["cases"]["bull"]["return_pct"] >= policy["minimum_bull_upside_pct"],
                  plausible_upside_screen=(result["cases"]["base"]["return_pct"] >= policy["minimum_base_upside_pct"]
                                           and result["cases"]["bull"]["return_pct"] >= policy["minimum_bull_upside_pct"]))
    return result


def authoritative_health(health, evidence, financial_to_usd, cap_usd):
    """Refresh risk inputs from the same statements used for admission."""
    result = dict(health or {})
    values = evidence["balance"]["values"]
    income = evidence["income"]["values"]
    for target, source in (("cash", "cash"), ("total_debt", "debt")):
        value = values.get(source)
        result[target] = value * financial_to_usd if value is not None else None
    debt, cash, equity = values.get("debt"), values.get("cash"), values.get("equity")
    result["net_debt"] = (debt - cash) * financial_to_usd if debt is not None and cash is not None else None
    result["debt_to_equity"] = debt / equity if debt is not None and equity is not None and equity > 0 else None
    result["debt_equity_display"] = result["debt_to_equity"]
    assets, liabilities = values.get("current_assets"), values.get("current_liabilities")
    result["current_ratio"] = assets / liabilities if assets is not None and liabilities is not None and liabilities > 0 else None
    result["revenue"] = income.get("revenue") * financial_to_usd if income.get("revenue") is not None else None
    result["debt_ebitda"] = debt / income["ebitda"] if debt is not None and income.get("ebitda") is not None and income["ebitda"] > 0 else None
    result.update(market_cap=cap_usd, monetary_currency="USD", debt_equity_source="dated_statement",
                  current_ratio_source="dated_statement", debt_equity_is_financial=False)
    return result
