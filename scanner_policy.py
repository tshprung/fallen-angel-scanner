"""Policy overlay for the daily fallen-angel scanner.

The overlay keeps the core scanner intact while:
1. extending the US universe into the upper slice of the Russell 2000;
2. applying stricter quality/valuation discipline to smaller companies.

The Russell-2000 holdings are fetched once per run from iShares' public
holdings endpoint. The fetch has JSON + CSV fallbacks because iShares can
occasionally return a non-JSON response to the AJAX endpoint.
"""

import csv
import io
import json
import time

import numpy as np
import requests
import fallen_angel_scanner as scanner

R2K_TOP_N = 750
R2K_MIN_DOLLAR_VOLUME = 2_000_000
R2K_MIN_MARKET_CAP = 750_000_000
R2K_MAX_MARKET_CAP = 2_000_000_000

IWM_JSON_URL = (
    "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
    "1467271812596.ajax?tab=all&fileType=json"
)
IWM_CSV_URL = (
    "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
)


def _ishares_headers():
    return {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf",
        "X-Requested-With": "XMLHttpRequest",
    }


def _to_number(value):
    if isinstance(value, dict):
        value = value.get("raw", value.get("display", 0))
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _clean_ticker(ticker):
    ticker = str(ticker or "").strip().strip('"')
    if not ticker or ticker in {"-", "nan", "None"}:
        return ""
    return ticker.replace(".", "-")


def _select_top_holdings(holdings):
    """Return the largest R2K constituents by current market value."""
    holdings = sorted(holdings, key=lambda x: x[0], reverse=True)
    result = []
    seen = set()
    for market_value, ticker in holdings:
        ticker = _clean_ticker(ticker)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        result.append(ticker)
        if len(result) >= R2K_TOP_N:
            break
    return result


def _parse_ishares_json(content):
    payload = json.loads(content.decode("utf-8-sig"))
    rows = payload.get("aaData") or payload.get("data") or []
    holdings = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        ticker = _clean_ticker(row[0])
        asset_class = str(row[3] or "").strip().lower()
        if not ticker or (asset_class and asset_class != "equity"):
            continue
        # iShares native schema: 4=market value, 5=weight.
        market_value = _to_number(row[4])
        holdings.append((market_value, ticker))
    return _select_top_holdings(holdings)


def _parse_ishares_csv(content):
    text = content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()

    # iShares puts descriptive metadata before the actual CSV header.
    header_index = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("ticker,"):
            header_index = i
            break
    if header_index is None:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
    holdings = []
    for row in reader:
        ticker = _clean_ticker(row.get("Ticker"))
        asset_class = str(row.get("Asset Class") or "").strip().lower()
        if not ticker or (asset_class and asset_class != "equity"):
            continue
        market_value = _to_number(row.get("Market Value"))
        holdings.append((market_value, ticker))

    return _select_top_holdings(holdings)


def fetch_upper_russell_2000():
    """Fetch the largest current IWM constituents with robust fallbacks."""
    session = requests.Session()
    headers = _ishares_headers()

    # JSON is the preferred machine-readable endpoint. Retry once because
    # iShares occasionally returns an empty/HTML response transiently.
    for attempt in range(2):
        try:
            response = session.get(IWM_JSON_URL, headers=headers, timeout=30)
            response.raise_for_status()
            result = _parse_ishares_json(response.content)
            if len(result) >= 500:
                print(f"  ✅ Russell 2000 extension: {len(result)} upper-slice tickers (JSON)")
                return result
            print(f"  ⚠️ iShares JSON returned only {len(result)} usable tickers")
        except Exception as e:
            print(f"  ⚠️ iShares JSON attempt {attempt + 1}/2 failed: {e}")
        if attempt == 0:
            time.sleep(2)

    # CSV is the documented download path and is a useful fallback when the
    # AJAX JSON response is blocked or malformed.
    try:
        response = session.get(IWM_CSV_URL, headers=headers, timeout=30)
        response.raise_for_status()
        result = _parse_ishares_csv(response.content)
        if len(result) >= 500:
            print(f"  ✅ Russell 2000 extension: {len(result)} upper-slice tickers (CSV)")
            return result
        print(f"  ⚠️ iShares CSV returned only {len(result)} usable tickers")
    except Exception as e:
        print(f"  ⚠️ iShares CSV fallback failed: {e}")

    print("  ❌ Russell 2000 extension unavailable — keeping base universe")
    return []


# Fetch once. The scanner is daily, so these are only two or three lightweight
# requests per run at worst, not per-ticker calls.
R2K_TICKERS = fetch_upper_russell_2000()
R2K_SET = set(R2K_TICKERS)


# ---------------------------------------------------------------------------
# Universe extension
# ---------------------------------------------------------------------------
_original_get_all_tickers = scanner.get_all_tickers


def get_all_tickers_with_upper_r2k():
    base = _original_get_all_tickers()
    combined = list(base) + R2K_TICKERS
    seen = set()
    unique = []
    for ticker in combined:
        if ticker not in seen:
            seen.add(ticker)
            unique.append(ticker)
    print(f"  📊 Scanner universe: {len(unique)} tickers after upper Russell 2000 extension")
    return unique


# ---------------------------------------------------------------------------
# Small-cap liquidity floor
# ---------------------------------------------------------------------------
_original_get_min_avg_dollar_volume_usd = scanner.get_min_avg_dollar_volume_usd


def get_min_avg_dollar_volume_usd_with_r2k(ticker):
    if ticker in R2K_SET:
        return R2K_MIN_DOLLAR_VOLUME
    return _original_get_min_avg_dollar_volume_usd(ticker)


# ---------------------------------------------------------------------------
# Recovery-target valuation sanity check
# ---------------------------------------------------------------------------
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

        market_cap = info.get("marketCap") or 0
        if R2K_MIN_MARKET_CAP <= market_cap < R2K_MAX_MARKET_CAP:
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
# Additional quality pressure for the $750M-$2B extension
# ---------------------------------------------------------------------------
_original_calculate_risk_score = scanner.calculate_risk_score


def calculate_risk_score_with_small_cap_quality(*args, **kwargs):
    score = _original_calculate_risk_score(*args, **kwargs)

    market_cap = kwargs.get("market_cap_usd")
    if market_cap is None and len(args) >= 7:
        market_cap = args[6]
    piotroski = kwargs.get("piotroski")
    if piotroski is None and len(args) >= 6:
        piotroski = args[5]
    debt_ebitda = kwargs.get("debt_ebitda")
    if debt_ebitda is None and len(args) >= 8:
        debt_ebitda = args[7]

    try:
        market_cap = float(market_cap or 0)
    except (TypeError, ValueError):
        market_cap = 0

    if R2K_MIN_MARKET_CAP <= market_cap < R2K_MAX_MARKET_CAP:
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


scanner.get_all_tickers = get_all_tickers_with_upper_r2k
scanner.get_min_avg_dollar_volume_usd = get_min_avg_dollar_volume_usd_with_r2k
scanner.estimate_recovery_target = estimate_recovery_target_with_valuation_sanity
scanner.calculate_risk_score = calculate_risk_score_with_small_cap_quality


if __name__ == "__main__":
    scanner.main()
