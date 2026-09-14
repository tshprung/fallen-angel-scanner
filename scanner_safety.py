"""Final safety guards for authoritative financial-risk data."""

import numpy as np

import fallen_angel_scanner as scanner


# The core leverage gate runs before the fixed financial-health calculation.
# Yahoo's quote-summary fields can disagree with the latest balance sheet,
# allowing a stock such as APLD to pass the early gate while the report later
# shows a materially higher D/E. Re-check leverage after the authoritative
# balance-sheet refresh so the admission decision and displayed numbers agree.
_ORIGINAL_STAGE2 = scanner.stage2_deep_analysis


def _authoritative_leverage_exclusion(stock):
    health = stock.get("financial_health") or {}
    if health.get("debt_equity_is_financial"):
        return None

    de = health.get("debt_to_equity")
    if de is not None:
        try:
            de = float(de)
            if np.isfinite(de) and de > scanner.MAX_DEBT_TO_EQUITY:
                return f"High debt (D/E: {de:.2f})"
        except (TypeError, ValueError):
            pass

    cap = health.get("market_cap") or stock.get("market_cap_usd") or stock.get("market_cap") or 0
    net_debt = health.get("net_debt")
    try:
        if net_debt is not None and float(net_debt) > 0 and float(cap) > 0:
            ratio = float(net_debt) / float(cap)
            if ratio >= scanner.NET_DEBT_TO_MCAP_MAX:
                return f"Equity stub: net debt {ratio:.1f}x market cap"
    except (TypeError, ValueError):
        pass
    return None


def _filter_authoritative_leverage(stocks):
    survivors = []
    rejected = []
    for stock in stocks or []:
        reason = _authoritative_leverage_exclusion(stock)
        if reason:
            ticker = stock.get("ticker", "?")
            stock["overlay_exclusion_reason"] = reason
            rejected.append(stock)
            print(f"  ⏭️  {ticker} removed by authoritative financial-risk guard: {reason}")
        else:
            survivors.append(stock)
    return survivors, rejected


def stage2_with_authoritative_leverage(candidates, memory):
    analyzed, fresh = _ORIGINAL_STAGE2(candidates, memory)

    analyzed, rejected_a = _filter_authoritative_leverage(analyzed)
    fresh, rejected_f = _filter_authoritative_leverage(fresh)

    existing = list(getattr(scanner, "_last_overlay_filtered_candidates", []) or [])
    scanner._last_overlay_filtered_candidates = existing + rejected_a + rejected_f
    return analyzed, fresh


scanner.stage2_deep_analysis = stage2_with_authoritative_leverage


# Missing liquidity data must not crash the run. Treat an unknown current
# ratio as neutral inside the original score calculation, then add one risk
# point so missing data cannot make a candidate look safer than a known value.
_ORIGINAL_RISK_SCORE = scanner.calculate_risk_score


def calculate_risk_score_safe(*args, **kwargs):
    health = args[0] if args else kwargs.get("financial_health")
    missing_current_ratio = isinstance(health, dict) and health.get("current_ratio") is None

    if missing_current_ratio:
        if args:
            args = list(args)
            safe_health = dict(args[0])
            safe_health["current_ratio"] = 1.0
            args[0] = safe_health
            args = tuple(args)
        else:
            safe_health = dict(health)
            safe_health["current_ratio"] = 1.0
            kwargs["financial_health"] = safe_health

    score = _ORIGINAL_RISK_SCORE(*args, **kwargs)
    if missing_current_ratio:
        score = min(10, int(score) + 1)
    return score


scanner.calculate_risk_score = calculate_risk_score_safe
