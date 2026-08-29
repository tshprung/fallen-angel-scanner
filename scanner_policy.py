"""Policy overlay for the daily fallen-angel scanner.

The overlay keeps the core scanner intact while extending the US universe into
smaller, liquid US companies and applying stricter discipline to them.

Primary extension: S&P 600. It is a much more reliable public source than the
IWM AJAX endpoint in GitHub Actions, and it gives us roughly 600 additional
small-cap names without adding thousands of Yahoo requests. IWM is retained
as an optional fallback because it is useful when its download endpoint works.
"""

import csv
import io
import json
import time

import numpy as np
import pandas as pd
import requests

import fallen_angel_scanner as scanner

R2K_TOP_N = 750
R2K_MIN_DOLLAR_VOLUME = 2_000_000
R2K_MIN_MARKET_CAP = 750_000_000
R2K_MAX_MARKET_CAP = 2_000_000_000

SP600_MIN_DOLLAR_VOLUME = 2_000_000
SP600_MIN_MARKET_CAP = 750_000_000

SMALL_CAP_MAX_MARKET_CAP_USD = 5_000_000_000
SMALL_CAP_MAX_RISK_SCORE = 2
SMALL_CAP_MIN_PIOTROSKI = 4
SMALL_CAP_MAX_DEBT_EBITDA = 5.0
SMALL_CAP_MAX_PRICE_TO_BOOK = 15.0
SMALL_CAP_MAX_NET_DEBT_TO_MCAP = 0.75

IWM_JSON_URL = (
    "https://www.ishares.com/us/products/239710/iwm-ishares-russell-2000-etf/"
    "1467271812596.ajax?tab=all&fileType=json"
)
IWM_CSV_URL = (
    "https://www.ishares.com/us/products/239710/iwm-ishares-russell-2000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
)
SP600_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"


def _ishares_headers():
    return {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.ishares.com/us/products/239710/iwm-ishares-russell-2000-etf",
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
    if not ticker or ticker.lower() in {"-", "nan", "none"}:
        return ""
    return ticker.replace(".", "-")


def _select_top_holdings(holdings):
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
        if not ticker:
            continue
        market_value = _to_number(row[4])
        holdings.append((market_value, ticker))
    return _select_top_holdings(holdings)


def _parse_ishares_csv(content):
    """Parse iShares CSV defensively; column names have changed over time."""
    text = content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    header_index = None
    for i, line in enumerate(lines):
        cells = [c.strip().strip('"').lower() for c in line.split(",")]
        if "ticker" in cells:
            header_index = i
            break
    if header_index is None:
        return []

    reader = csv.reader(io.StringIO("\n".join(lines[header_index:])))
    try:
        header = [h.strip().strip('"') for h in next(reader)]
    except StopIteration:
        return []

    normalized = {h.lower(): i for i, h in enumerate(header)}
    ticker_idx = normalized.get("ticker")
    if ticker_idx is None:
        return []

    value_idx = normalized.get("market value")
    if value_idx is None:
        value_idx = normalized.get("market value ($)")
    if value_idx is None:
        value_idx = normalized.get("weight (%)")

    holdings = []
    for row in reader:
        if ticker_idx >= len(row):
            continue
        ticker = _clean_ticker(row[ticker_idx])
        if not ticker:
            continue
        value = _to_number(row[value_idx]) if value_idx is not None and value_idx < len(row) else 0.0
        holdings.append((value, ticker))

    return _select_top_holdings(holdings)


def fetch_upper_russell_2000():
    """Best-effort IWM fetch. Returns [] when iShares blocks automation clients."""
    session = requests.Session()
    headers = _ishares_headers()
    for attempt in range(2):
        try:
            response = session.get(IWM_JSON_URL, headers=headers, timeout=20)
            response.raise_for_status()
            result = _parse_ishares_json(response.content)
            if len(result) >= 500:
                print(f"  ✅ IWM/Russell 2000 extension: {len(result)} tickers (JSON)")
                return result
        except Exception as e:
            print(f"  ⚠️ IWM JSON attempt {attempt + 1}/2 failed: {e}")
        if attempt == 0:
            time.sleep(2)

    try:
        response = session.get(IWM_CSV_URL, headers=headers, timeout=20)
        response.raise_for_status()
        result = _parse_ishares_csv(response.content)
        if len(result) >= 500:
            print(f"  ✅ IWM/Russell 2000 extension: {len(result)} tickers (CSV)")
            return result
    except Exception as e:
        print(f"  ⚠️ IWM CSV fallback failed: {e}")
    return []


def fetch_sp600_tickers():
    """Fetch the current S&P 600 constituent list from Wikipedia."""
    try:
        response = requests.get(
            SP600_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FallenAngelScanner/1.0)"},
            timeout=20,
        )
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        for table in tables:
            for column in ("Symbol", "Ticker symbol", "Ticker"):
                if column in table.columns:
                    result = []
                    seen = set()
                    for raw in table[column].dropna().astype(str):
                        ticker = _clean_ticker(raw)
                        if ticker and ticker not in seen:
                            seen.add(ticker)
                            result.append(ticker)
                    if len(result) >= 500:
                        print(f"  ✅ S&P 600 extension: {len(result)} tickers from Wikipedia")
                        return result
    except Exception as e:
        print(f"  ⚠️ S&P 600 fetch failed: {e}")
    return []


SP600_TICKERS = fetch_sp600_tickers()
IWM_TICKERS = fetch_upper_russell_2000() if not SP600_TICKERS else []
EXTENSION_TICKERS = SP600_TICKERS or IWM_TICKERS
EXTENSION_SET = set(EXTENSION_TICKERS)


_original_get_all_tickers = scanner.get_all_tickers


def get_all_tickers_with_extension():
    base = _original_get_all_tickers()
    combined = list(base) + EXTENSION_TICKERS
    seen = set()
    unique = []
    for ticker in combined:
        if ticker not in seen:
            seen.add(ticker)
            unique.append(ticker)
    label = "S&P 600" if SP600_TICKERS else "upper Russell 2000"
    print(f"  📊 Scanner universe: {len(unique)} tickers after {label} extension")
    return unique


_original_get_min_avg_dollar_volume_usd = scanner.get_min_avg_dollar_volume_usd


def get_min_avg_dollar_volume_usd_with_extension(ticker):
    if ticker in EXTENSION_SET:
        return SP600_MIN_DOLLAR_VOLUME if SP600_TICKERS else R2K_MIN_DOLLAR_VOLUME
    return _original_get_min_avg_dollar_volume_usd(ticker)


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
        word in industry for word in ("bank", "insurance", "reit", "capital market", "asset management")
    )

    if not is_financial:
        forward_pe = info.get("forwardPE")
        price_to_book = info.get("priceToBook")
        haircut = 1.0
        if isinstance(forward_pe, (int, float)) and forward_pe > 35:
            haircut *= 0.85
        if isinstance(price_to_book, (int, float)) and price_to_book > 6:
            haircut *= 0.85
        if haircut < 1.0:
            target_low = current_price + (target_low - current_price) * haircut
            target_high = current_price + (target_high - current_price) * haircut
            upside_pct = (target_high / current_price - 1) * 100

    return target_low, target_high, upside_pct


_original_search_recent_news = scanner.search_recent_news


def search_recent_news_with_neutral_fallback(ticker, company_name):
    """Do not label an unverified price-only inference as earnings/news."""
    headlines = _original_search_recent_news(ticker, company_name)
    synthetic_markers = (
        "sharp drop detected",
        "moderate decline",
        "gradual decline",
        "price decline detected",
        "unable to determine cause",
    )
    if headlines and any(
        any(marker in str(headline).lower() for marker in synthetic_markers)
        for headline in headlines
    ):
        return ["No verified recent news available — price action only"]
    return headlines


# ---------------------------------------------------------------------------
# Catalyst / cause analysis
# ---------------------------------------------------------------------------
SERIOUS_CAUSE_KEYWORDS = (
    "fraud", "investigation", "sec inquiry", "criminal", "scandal", "bankruptcy",
    "default", "delisting", "recall", "accounting irregular", "restatement",
    "going concern", "covenant breach", "liquidity crisis", "chapter 11",
)
TEMPORARY_CAUSE_KEYWORDS = (
    "earnings", "guidance", "outlook", "forecast", "revenue miss", "profit miss",
    "eps miss", "analyst downgrade", "downgrade", "sector selloff", "sector rotation",
    "market selloff", "profit-taking", "valuation", "tariff", "macro", "weak demand",
)


def classify_drop_cause(stock_record):
    """Classify the known evidence behind a drop; never infer a cause from price alone."""
    headlines = stock_record.get("news_headlines") or []
    text = " ".join(str(h) for h in headlines).lower()
    synthetic = "no verified recent news" in text or "price action only" in text

    if synthetic or not text.strip():
        return {
            "cause_class": "unclear",
            "cause_confidence": "LOW",
            "cause_label": "🟡 CAUSE UNCLEAR",
            "cause_detail": "No verified catalyst found; price action alone is not treated as a cause.",
        }

    serious_hits = [k for k in SERIOUS_CAUSE_KEYWORDS if k in text]
    temporary_hits = [k for k in TEMPORARY_CAUSE_KEYWORDS if k in text]

    if serious_hits:
        return {
            "cause_class": "structural_risk",
            "cause_confidence": "MEDIUM",
            "cause_label": "🔴 STRUCTURAL RISK",
            "cause_detail": f"Recent coverage contains: {', '.join(serious_hits[:3])}.",
        }

    if temporary_hits:
        health = stock_record.get("financial_health") or {}
        rev = health.get("revenue_growth_yoy")
        piotroski = stock_record.get("piotroski_score")
        supportive = (rev is not None and rev >= 0) and (piotroski is None or piotroski >= 5)
        if supportive:
            return {
                "cause_class": "potential_overreaction",
                "cause_confidence": "MEDIUM",
                "cause_label": "🟢 POTENTIAL OVERREACTION",
                "cause_detail": f"Coverage points to {', '.join(temporary_hits[:3])}; current business metrics do not show an obvious broad deterioration.",
            }
        return {
            "cause_class": "temporary_candidate",
            "cause_confidence": "LOW",
            "cause_label": "🟡 POSSIBLY TEMPORARY",
            "cause_detail": f"Coverage points to {', '.join(temporary_hits[:3])}, but fundamentals do not yet confirm an overreaction.",
        }

    return {
        "cause_class": "unclear",
        "cause_confidence": "LOW",
        "cause_label": "🟡 CAUSE UNCLEAR",
        "cause_detail": "Recent headlines were found, but they do not identify a reliable reason for the decline.",
    }


def _apply_catalyst_analysis(stocks):
    result = []
    for stock in stocks:
        cause = classify_drop_cause(stock)
        stock.update(cause)

        if cause["cause_class"] == "structural_risk":
            print(f"  ⏭️  {stock['ticker']} removed by catalyst gate: {cause['cause_detail']}")
            continue

        # Unknown cause is deliberately a WATCH, never an automatic BUY.
        if cause["cause_class"] == "unclear":
            stock["catalyst_status"] = "WATCH"
            # Do not fabricate a technical entry range or overwrite the
            # scanner's bottom detection. The absence of verified news is
            # uncertainty, not evidence that the price should be lower.
        else:
            stock["catalyst_status"] = "PASS"

        result.append(stock)
    return result


# ---------------------------------------------------------------------------
# Small-cap quality overlay
# ---------------------------------------------------------------------------
_original_stage2_deep_analysis = scanner.stage2_deep_analysis


def _filter_small_cap_results(stocks):
    filtered = []
    for stock in stocks:
        ticker = stock.get("ticker")
        if ticker not in EXTENSION_SET:
            filtered.append(stock)
            continue

        cap = stock.get("market_cap_usd") or 0
        health = stock.get("financial_health") or {}
        net_debt = health.get("net_debt")
        debt_ebitda = health.get("debt_ebitda")
        pb = stock.get("price_to_book")
        risk = stock.get("risk_score")
        piotroski = stock.get("piotroski_score")
        piotroski_checks = stock.get("piotroski_checks")

        if cap and cap > SMALL_CAP_MAX_MARKET_CAP_USD:
            print(f"  ⏭️  {ticker} removed by small-cap cap limit: ${cap / 1e9:.1f}B > ${SMALL_CAP_MAX_MARKET_CAP_USD / 1e9:.1f}B")
            continue
        if risk is not None and risk > SMALL_CAP_MAX_RISK_SCORE:
            print(f"  ⏭️  {ticker} removed by small-cap risk limit: {risk}/10 > {SMALL_CAP_MAX_RISK_SCORE}")
            continue
        if piotroski is not None and piotroski_checks is not None and piotroski_checks >= 6 and piotroski < SMALL_CAP_MIN_PIOTROSKI:
            print(f"  ⏭️  {ticker} removed by small-cap Piotroski floor: F{piotroski}/{piotroski_checks}")
            continue
        if debt_ebitda is not None and np.isfinite(float(debt_ebitda)) and float(debt_ebitda) > SMALL_CAP_MAX_DEBT_EBITDA:
            print(f"  ⏭️  {ticker} removed by small-cap debt/EBITDA limit: {debt_ebitda:.1f}x > {SMALL_CAP_MAX_DEBT_EBITDA:.1f}x")
            continue
        if net_debt is not None and cap and net_debt > 0 and (net_debt / cap) >= SMALL_CAP_MAX_NET_DEBT_TO_MCAP:
            ratio = net_debt / cap
            print(f"  ⏭️  {ticker} removed by small-cap net-debt limit: {ratio:.1f}x market cap >= {SMALL_CAP_MAX_NET_DEBT_TO_MCAP:.2f}x")
            continue
        if pb is not None and np.isfinite(float(pb)) and float(pb) > SMALL_CAP_MAX_PRICE_TO_BOOK:
            print(f"  ⏭️  {ticker} removed by small-cap P/B sanity limit: {pb:.1f}x > {SMALL_CAP_MAX_PRICE_TO_BOOK:.1f}x")
            continue
        filtered.append(stock)
    return filtered


def stage2_deep_analysis_with_small_cap_policy(candidates, memory):
    analyzed, fresh_crash = _original_stage2_deep_analysis(candidates, memory)
    analyzed = _apply_catalyst_analysis(_filter_small_cap_results(analyzed))
    fresh_crash = _apply_catalyst_analysis(_filter_small_cap_results(fresh_crash))
    return analyzed, fresh_crash


scanner.get_all_tickers = get_all_tickers_with_extension
scanner.get_min_avg_dollar_volume_usd = get_min_avg_dollar_volume_usd_with_extension
scanner.estimate_recovery_target = estimate_recovery_target_with_valuation_sanity
scanner.search_recent_news = search_recent_news_with_neutral_fallback
scanner.stage2_deep_analysis = stage2_deep_analysis_with_small_cap_policy


if __name__ == "__main__":
    scanner.main()
