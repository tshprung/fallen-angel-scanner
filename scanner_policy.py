"""Policy overlay for the daily fallen-angel scanner.

Keeps the main scanner logic unchanged while adding stricter quality controls
for the newly added upper-small-cap universe and a valuation sanity check for
all operating companies. This file is intentionally lightweight: it does not
add any external API calls.
"""

import numpy as np
import fallen_angel_scanner as scanner


# ---------------------------------------------------------------------------
# 1. Recovery-target valuation sanity check
# ---------------------------------------------------------------------------
# The original target model can produce very large upside from historical
# prices/analyst targets even when the stock remains extremely expensive.
# Apply a haircut to the *upside*, rather than a hard valuation exclusion, so
# genuine high-growth recoveries can still qualify.
_original_estimate_recovery_target = scanner.estimate_recovery_target


def estimate_recovery_target_with_valuation_sanity(stock, info, current_price):
    target_low, target_high, upside_pct = _original_estimate_recovery_target(
        stock, info, current_price
    )
    if upside_pct is None or not np.isfinite(upside_pct) or upside_pct <= 0:
        return target_low, target_high, upside_pct

    sector = (info.get("sector") or "").strip().lower()
    industry = (info.get("industry") or "").strip().lower()
    is_financial = sector in ("financial services", "real estate") or any(
        word in industry
        for word in ("bank", "insurance", "reit", "capital market", "asset management")
    )

    if not is_financial:
        forward_pe = info.get("forwardPE")
        price_to_book = info.get("priceToBook")
        try:
            fpe = float(forward_pe) if forward_pe is not None else None
        except (TypeError, ValueError):
            fpe = None
        try:
            pb = float(price_to_book) if price_to_book is not None else None
        except (TypeError, ValueError):
            pb = None

        haircut = 0.0
        if fpe is not None and fpe > 35:
            haircut += 0.15
        if pb is not None and pb > 6:
            haircut += 0.15

        # For the upper small-cap extension, demand a little more valuation
        # discipline because these names have higher failure/dispersion risk.
        market_cap = info.get("marketCap") or 0
        if 750_000_000 <= market_cap < 2_000_000_000:
            if fpe is not None and fpe > 30:
                haircut += 0.10
            if pb is not None and pb > 5:
                haircut += 0.10

        if haircut > 0:
            haircut = min(haircut, 0.40)
            adjusted_upside = upside_pct * (1.0 - haircut)
            target_avg = current_price * (1.0 + adjusted_upside / 100.0)
            target_low = target_avg * 0.90
            target_high = target_avg * 1.10
            return target_low, target_high, adjusted_upside

    return target_low, target_high, upside_pct


# ---------------------------------------------------------------------------
# 2. Additional small-cap quality pressure
# ---------------------------------------------------------------------------
_original_calculate_risk_score = scanner.calculate_risk_score


def calculate_risk_score_with_small_cap_quality(*args, **kwargs):
    score = _original_calculate_risk_score(*args, **kwargs)

    # calculate_risk_score signature has market_cap_usd, piotroski and
    # debt_ebitda as keyword arguments in the current scanner.
    market_cap = kwargs.get("market_cap_usd")
    if market_cap is None and len(args) >= 7:
        market_cap = args[6]
    piotroski = kwargs.get("piotroski")
    if piotroski is None and len(args) >= 6:
        piotroski = args[5]
    debt_ebitda = kwargs.get("debt_ebitda")
    if debt_ebitda is None and len(args) >= 7:
        debt_ebitda = args[6]

    try:
        market_cap = float(market_cap or 0)
    except (TypeError, ValueError):
        market_cap = 0

    if 750_000_000 <= market_cap < 2_000_000_000:
        try:
            if debt_ebitda is not None and np.isfinite(float(debt_ebitda)) and float(debt_ebitda) > 3.5:
                score += 1
        except (TypeError, ValueError):
            pass
        try:
            if piotroski is not None and int(piotroski) < 4:
                score += 1
        except (TypeError, ValueError):
            pass

    return max(1, min(10, round(score)))


scanner.estimate_recovery_target = estimate_recovery_target_with_valuation_sanity
scanner.calculate_risk_score = calculate_risk_score_with_small_cap_quality


if __name__ == "__main__":
    scanner.main()
