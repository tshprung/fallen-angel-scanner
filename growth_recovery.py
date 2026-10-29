"""Bounded prospective growth research. Never creates a selection or clears risk."""

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from fundamental_analysis import collect_evidence, load_policy, assess_solvency, specialist_requirements
from scanner_currency import finite

METHOD = {
    "version": 1, "minimum_quarterly_revenue_growth_pct": 15,
    "minimum_current_debt_coverage": 1.25, "fcf_stress_fraction": .75,
    "maximum_annual_share_growth": .10, "daily_company_budget": 12,
    "description": "Exploratory thresholds, not calibrated return or survival probabilities",
}
METHOD_ID = sha256(json.dumps(METHOD, sort_keys=True).encode()).hexdigest()[:12]
NOTICE = ("Shadow research only. No valuation, 2x prediction, financial clearance or investment selection. "
          "Cash excludes investments; covenants, restricted cash, lease treatment, stock compensation, "
          "debt due in months 13-24, filings and catalysts require manual review. "
          "No historical performance or success rate has been established.")


def revenue_growth(frame, now, maximum_age):
    """Same-season quarter comparison; never annualize one quarter or use future periods."""
    if not isinstance(frame, pd.DataFrame) or "Total Revenue" not in frame.index:
        return {"status": "UNVERIFIED", "reason": "Quarterly revenue unavailable"}
    dates = pd.to_datetime(frame.columns, errors="coerce", utc=True)
    if dates.isna().any() or dates.has_duplicates or not frame.index.is_unique:
        return {"status": "UNVERIFIED", "reason": "Ambiguous statement dates or rows"}
    pairs = sorted(((date, col) for date, col in zip(dates, frame.columns)
                    if date.date() <= now.date()), reverse=True)[:5]
    if len(pairs) < 5:
        return {"status": "UNVERIFIED", "reason": "Five consecutive quarterly revenues required"}
    gaps = [(pairs[i][0] - pairs[i+1][0]).days for i in range(4)]
    if any(not 60 <= gap <= 120 for gap in gaps) or not 330 <= (pairs[0][0]-pairs[4][0]).days <= 400:
        return {"status": "UNVERIFIED", "reason": "Quarterly revenue periods do not align"}
    if not 0 <= (now.date()-pairs[0][0].date()).days <= maximum_age:
        return {"status": "UNVERIFIED", "reason": "Quarterly revenue stale"}
    values = [finite(frame.loc["Total Revenue", col]) for _, col in pairs]
    if any(value is None or value <= 0 for value in values):
        return {"status": "UNVERIFIED", "reason": "Invalid quarterly revenues"}
    return {"status": "AVAILABLE", "asof": pairs[0][0].date().isoformat(),
            "comparison_asof": pairs[4][0].date().isoformat(),
            "latest_revenue": values[0], "year_ago_revenue": values[4],
            "growth_pct": (values[0]/values[4]-1)*100}


def assess_growth(evidence, info, growth, policy):
    """Interest coverage/price shape remain visible but do not define this research queue."""
    result = {"status": "UNVERIFIED", "reasons": [], "metrics": {}, "revenue_growth": growth,
              "review_required": True, "selection_eligible": False}
    missing, rejected = [], []
    if specialist_requirements(info):
        result.update(status="NOT_MATCHED", reasons=["Specialist financial model required"])
        return result
    if not info.get("sector") or not info.get("financialCurrency"):
        missing.append("Sector or financial currency missing")
    if growth.get("status") != "AVAILABLE":
        missing.append(growth.get("reason", "Revenue growth unverified"))
    elif growth["growth_pct"] < METHOD["minimum_quarterly_revenue_growth_pct"]:
        rejected.append("Quarterly revenue growth below exploratory threshold")
    periods = []
    for name in ("balance", "cashflow", "income"):
        block = evidence[name]
        age = finite(block.get("age_days"))
        if age is None or not 0 <= age <= policy["fresh_statement_days"]:
            missing.append(f"Fresh {name} statement required")
        date = pd.to_datetime(block.get("asof"), errors="coerce", utc=True)
        if pd.isna(date):
            missing.append(f"Usable {name} period required")
        else:
            periods.append(date)
        if name != "balance" and block.get("basis") != "ttm_quarterly":
            missing.append(f"Four consecutive quarters required for {name}")
    if growth.get("asof"):
        periods.append(pd.Timestamp(growth["asof"], tz="UTC"))
    if periods and (max(periods)-min(periods)).days > 120:
        missing.append("Statement periods do not align within 120 days")
    balance = evidence["balance"]["values"]
    cash, debt, current = (finite(balance.get(key)) for key in ("cash", "debt", "current_debt"))
    ocf, fcf = (finite(evidence["cashflow"]["values"].get(key)) for key in ("ocf", "fcf"))
    interest = finite(evidence["income"]["values"].get("interest"))
    if any(value is None or value < 0 for value in (cash, debt, current)):
        missing.append("Nonnegative cash, total debt and current debt required")
    if current is not None and debt is not None and current > debt:
        missing.append("Current debt exceeds total debt; reconcile source")
    if ocf is None or fcf is None:
        missing.append("Operating and free cash flow required")
    elif ocf <= 0 or fcf <= 0:
        rejected.append("Positive trailing operating and free cash flow required")
    funding = None
    if debt is not None and debt > 0 and interest is None:
        missing.append("Gross interest expense required for funding buffer")
    elif fcf is not None and debt is not None:
        funding = fcf - abs(interest or 0)
        result["metrics"]["fcf_after_additional_interest_buffer"] = funding
        if funding <= 0:
            rejected.append("Positive cash flow after financing buffer required")
    if cash is not None and cash >= 0 and current is not None and current > 0 and funding is not None:
        coverage = (cash+METHOD["fcf_stress_fraction"]*max(funding, 0))/current
        result["metrics"]["current_debt_coverage"] = coverage
        if coverage < METHOD["minimum_current_debt_coverage"]:
            rejected.append("Cash plus stressed cash flow insufficient for current debt")
    dilution = finite(evidence.get("annual_share_growth"))
    share_age = finite(evidence.get("annual_share_growth_age_days"))
    if share_age is None or not 0 <= share_age <= policy["max_annual_statement_days"]:
        missing.append("Fresh annual share-count comparison required")
    if dilution is None or dilution < -1:
        missing.append("Usable annual share-count growth required")
    elif dilution > METHOD["maximum_annual_share_growth"]:
        rejected.append("Annual share-count growth above exploratory threshold")
    result["metrics"].update(cash=cash, total_debt=debt, current_debt=current,
                             annual_share_growth=dilution)
    result.update(status="NOT_MATCHED" if rejected else "UNVERIFIED" if missing else "OBSERVE_REVIEW_REQUIRED",
                  reasons=rejected+missing)
    return result


def run_shadow(candidates, audit, fetch, output_dir, now=None, budget=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    now = now.tz_convert("UTC")
    policy = load_policy()
    budget = METHOD["daily_company_budget"] if budget is None else budget
    if type(budget) is not int or not 1 <= budget <= METHOD["daily_company_budget"]:
        raise ValueError("Shadow budget must be between 1 and 12")
    by_ticker = {item["ticker"]: item for item in candidates}
    symbols = sorted(by_ticker)
    # Full batches rotate, including through names rejected before core financial collection.
    offset = (now.date().toordinal()*budget) % len(symbols) if symbols else 0
    chosen = set((symbols[offset:]+symbols[:offset])[:budget])
    audits = {item["ticker"]: item for item in audit}
    records = []
    for symbol in symbols:
        original = audits.get(symbol, {})
        candidate = by_ticker[symbol]
        record = {"ticker": symbol, "status": "DEFERRED_BUDGET", "selection_eligible": False,
                  "observed_price": candidate.get("current_price"),
                  "currency_context": candidate.get("currency_context"),
                  "market_cap_usd": candidate.get("market_cap_usd"),
                  "core_decision": original.get("decision"), "core_reason": original.get("reason"),
                  "price_dislocation": {key: candidate.get(key) for key in
                    ("drop_21d_pct", "drop_recent_peak_pct", "recent_peak_date")}}
        if symbol in chosen:
            try:
                stock, info = fetch(symbol)
                if stock is None or not info:
                    raise ValueError("Quote source unavailable")
                evidence = collect_evidence(stock, info, now=now, policy=policy)
                annual_dates = pd.to_datetime(stock.balance_sheet.columns, errors="coerce", utc=True)
                usable_dates = sorted((date for date in annual_dates if not pd.isna(date)
                                       and date.date() <= now.date()), reverse=True)
                if len(set(usable_dates)) == len(usable_dates) and len(usable_dates) >= 2:
                    evidence["annual_share_growth_age_days"] = (now.date()-usable_dates[0].date()).days
                    evidence["annual_share_growth_asof"] = usable_dates[0].date().isoformat()
                growth = revenue_growth(stock.quarterly_income_stmt, now, policy["fresh_statement_days"])
                record.update(assess_growth(evidence, info, growth, policy))
                record["statement_snapshot"] = {
                    name: {key: evidence[name].get(key) for key in ("asof", "basis", "periods", "values")}
                    for name in ("balance", "cashflow", "income")}
                record["share_comparison_asof"] = evidence.get("annual_share_growth_asof")
                record.update(financial_evidence=evidence, ordinary_solvency=assess_solvency(evidence, info, policy),
                              financial_currency=info.get("financialCurrency"),
                              official_filing_check=original.get("official_filing_check"),
                              review_hold=original.get("review_hold"))
            except Exception as exc:
                record.update(status="SOURCE_ERROR", reasons=[type(exc).__name__])
        records.append(record)
    report = {"generated_at": now.isoformat(), "method": METHOD, "method_id": METHOD_ID,
              "policy_id": policy["id"], "notice": NOTICE, "universe": "Current Stage 1 price candidates only",
              "counts": dict(Counter(row["status"] for row in records)), "records": records}
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    # Keep compact immutable first observations per date/method/policy/symbol.
    history_path = directory / "growth_recovery_shadow_history.json"
    history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
    keys = {(row["date"], row["method_id"], row["policy_id"], row["ticker"]) for row in history}
    for record in records:
        if record["status"] == "DEFERRED_BUDGET":
            continue
        key = (now.date().isoformat(), METHOD_ID, policy["id"], record["ticker"])
        if key not in keys:
            history.append({"date": key[0], "method_id": METHOD_ID, "policy_id": policy["id"],
                            "observed_at": now.isoformat(), **{k: v for k, v in record.items() if k != "financial_evidence"}})
            keys.add(key)
    from research_reporting import clean
    for path, value in ((history_path, history), (directory/"growth_recovery_shadow.json", report)):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(clean(value), indent=2, allow_nan=False)+"\n", encoding="utf-8")
        temporary.replace(path)
    lines = ["# Growth recovery shadow research", "", NOTICE, "",
             f"Generated: {now.isoformat()}; method {METHOD_ID}; core policy {policy['id']}.", "",
             "Only current Stage 1 candidates are covered; the daily budget rotates without ranking winners.", "",
             "| Ticker | Shadow outcome | Core decision | Reasons |", "|---|---|---|---|"]
    def cell(value):
        return str(value or "").replace("|", "/").replace("\n", " ").replace("\r", " ")
    for row in records:
        lines.append("| " + " | ".join(cell(value) for value in
            (row["ticker"], row["status"], row["core_decision"], "; ".join(row.get("reasons", [])))) + " |")
    (directory/"growth_recovery_shadow.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    return {"status": "COLLECTED", "method_id": METHOD_ID, "counts": report["counts"],
            "notice": NOTICE}
