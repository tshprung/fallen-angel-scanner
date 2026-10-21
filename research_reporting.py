"""Inspectable research output and escaped financial evidence in email."""

from datetime import datetime, timezone
from html import escape
import json
import math
from pathlib import Path

from filing_review import write_filing_queue, filing_links_html


def clean(value):
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(item) for item in value]
    if hasattr(value, "item"):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_research_report(audit, selected, prefix="research_report", scope=None):
    data = clean({"generated_at": datetime.now(timezone.utc).isoformat(),
                  "selected_tickers": [stock["ticker"] for stock in selected],
                  "scan_scope": scope or {"type": "unspecified"},
                  "candidates": audit,
                  "notice": "Research screens and illustrative sensitivities; no guaranteed return or survival probability"})
    Path(f"{prefix}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Financial research report", "", data["notice"], "",
             f"Generated: {data['generated_at']}", "",
             f"Scope: {data['scan_scope'].get('type')}; symbols: {', '.join(data['scan_scope'].get('symbols', [])) or 'configured universe / see run logs'}.", "",
             f"Selected for research: {', '.join(data['selected_tickers']) or 'none'}.", "",
             "| Ticker | Decision | Solvency | Base sensitivity | Bull sensitivity | Main reason |",
             "|---|---|---|---:|---:|---|"]
    def text(value):
        return str(value).replace("|", "/").replace("\n", " ")
    for item in audit:
        solvency = item.get("solvency") or {}
        valuation = item.get("valuation") or {}
        cases = valuation.get("cases") or {}
        def upside(name):
            value = cases.get(name, {}).get("return_pct")
            return f"{value:+.1f}%" if value is not None else "unavailable"
        reasons = solvency.get("flags", []) + solvency.get("missing", []) + solvency.get("review", [])
        reason = item.get("reason") or (reasons[0] if reasons else "")
        lines.append(f"| {text(item['ticker'])} | {text(item.get('decision', 'not_selected'))} | {solvency.get('status', 'not_evaluated')} | {upside('base')} | {upside('bull')} | {text(reason)} |")
    lines += ["", "Full statement period ends, row labels, missing fields, assumptions and exclusions are in research_report.json.",
              "A REVIEW status commonly means the 13–24 month contractual debt schedule still needs filing review. UNVERIFIED and SPECIALIST_REVIEW candidates cannot enter the ordinary-company shortlist.",
              "An empty shortlist is a valid result. Scenario assumptions are configurable in research_policy.json and are not empirically calibrated predictions."]
    Path(f"{prefix}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_filing_queue(audit, Path(prefix).with_name("filing_review.md"))
    return data


def candidate_needs_review(stock):
    return (stock.get("catalyst_status") == "WATCH"
            or stock.get("solvency_status") in ("REVIEW", "UNVERIFIED", "SPECIALIST_REVIEW")
            or stock.get("risk_score_raw", stock.get("risk_score", 10)) >= 4)


def financial_detail_html(stock):
    solvency = stock.get("solvency")
    valuation = stock.get("valuation")
    if not solvency and not valuation:
        return ""
    evidence = stock.get("financial_evidence") or {}
    parts = ["<div><h4>Financial evidence and valuation sensitivities</h4>"]
    if solvency:
        parts.append(f"<p><strong>Solvency screen: {escape(solvency['status'])}</strong> (not a survival guarantee)</p>")
        messages = solvency["flags"] + solvency["missing"] + solvency["review"]
        if messages:
            parts.append("<ul>" + "".join(f"<li>{escape(message)}</li>" for message in messages) + "</ul>")
        metrics = solvency.get("metrics", {})
        labels = {"interest_coverage": "EBIT / interest (x)", "debt_equity": "Debt / equity (x)",
                  "net_debt_ebitda": "Net debt / EBITDA (x)", "current_debt_coverage": "Current-debt coverage (x)",
                  "cash_runway_months": "Cash runway (months)", "current_ratio": "Current ratio (x)",
                  "fcf_after_interest_buffer": f"Annual cash-flow proxy after buffer ({evidence.get('financial_currency')})"}
        parts.append("<p>" + " | ".join(f"{escape(labels.get(name, name))}: {value:,.2f}" for name, value in metrics.items()) + "</p>")
    dates = []
    for name in ("balance", "cashflow", "income"):
        block = evidence.get(name, {})
        if block:
            dates.append(f"{name}: {block.get('asof') or 'unavailable'} ({block.get('basis')})")
    parts.append("<p>Statement period ends: " + escape("; ".join(dates)) + ". Filing dates are not verified.</p>")
    if valuation and valuation.get("status") == "SENSITIVITY":
        parts.append(f"<p>{escape(valuation['description'])}. Assumed share dilution: {valuation['assumed_share_dilution']:.0%}. No probabilities assigned.</p>")
        parts.append("<table><tr><th>Case</th><th>FCF factor</th><th>Equity FCF multiple</th><th>Price (quote units)</th><th>Return</th></tr>")
        for name, case in valuation["cases"].items():
            parts.append(f"<tr><td>{escape(name)}</td><td>{case['fcf_factor']:.2f}</td><td>{case['equity_fcf_multiple']:.1f}x</td><td>{case['price']:.2f} {escape(stock['currency'])}</td><td>{case['return_pct']:+.1f}%</td></tr>")
        parts.append("</table><p>A bull case at 2× is a sensitivity flag, not a one-year forecast.</p>")
    elif valuation:
        parts.append("<p>Valuation unavailable: " + escape(valuation.get("reason") or "insufficient data") + "</p>")
    parts.append(filing_links_html(stock.get("filing_review")))
    parts.append(f"<p>Research policy: {escape(evidence.get('policy_id') or '')}</p></div>")
    return "".join(parts)
