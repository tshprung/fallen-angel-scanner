"""Targeted production bug fixes for the Fallen Angel Scanner."""

import re
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

import fallen_angel_scanner as scanner

# Re-analyze every Stage 2 candidate on every run. The scanner normally keeps
# sent-stock memory to prevent duplicate alerts, but this project is typically
# run once per day and each run should reflect the current market state. Memory
# remains available for tracking/audit and price alerts; it is no longer a gate
# on fresh Stage 2 analysis.
def should_send_stock_every_run(ticker, memory):
    return True

scanner.should_send_stock = should_send_stock_every_run

_original_get_financial_health = scanner.get_financial_health


def _latest_balance_value(df, labels):
    if df is None or df.empty:
        return None
    for label in labels:
        if label in df.index:
            try:
                series = pd.to_numeric(df.loc[label], errors="coerce").dropna()
                if not series.empty:
                    value = float(series.iloc[0])
                    return value if np.isfinite(value) else None
            except Exception:
                return None
    return None


def get_financial_health_fixed(ticker_obj):
    health = _original_get_financial_health(ticker_obj)
    if health is None:
        return None
    try:
        info = ticker_obj.info
    except Exception as exc:
        print(f"    ⚠️ Financial info refresh failed: {exc}")
        info = {}
    try:
        bs = ticker_obj.balance_sheet
    except Exception as exc:
        print(f"    ⚠️ Balance-sheet fetch failed: {exc}")
        bs = None

    current_assets = _latest_balance_value(bs, ("Current Assets",))
    current_liabilities = _latest_balance_value(bs, ("Current Liabilities",))
    if current_assets is None:
        value = info.get("totalCurrentAssets")
        current_assets = float(value) if value is not None and np.isfinite(float(value)) else None
    if current_liabilities is None:
        value = info.get("totalCurrentLiabilities")
        current_liabilities = float(value) if value is not None and np.isfinite(float(value)) else None
    if current_assets is not None and current_liabilities is not None:
        if current_liabilities > 0:
            health["current_ratio"] = round(current_assets / current_liabilities, 2)
        elif current_assets > 0:
            health["current_ratio"] = 99.0
        else:
            health["current_ratio"] = None
        health["current_ratio_source"] = "balance_sheet" if bs is not None else "quote_summary"
        print(f"    💧 Current ratio: {health['current_ratio']} ({health['current_ratio_source']})")
    else:
        health["current_ratio"] = None
        health["current_ratio_source"] = "unavailable"
        print("    ⚠️ Current ratio unavailable: missing current-assets/current-liabilities data")

    equity = _latest_balance_value(bs, ("Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"))
    debt = _latest_balance_value(bs, ("Total Debt", "Total Debt And Capital Lease Obligation"))
    if debt is None:
        value = info.get("totalDebt")
        debt = float(value) if value is not None and np.isfinite(float(value)) else None
    if equity is None:
        value = info.get("totalStockholderEquity")
        equity = float(value) if value is not None and np.isfinite(float(value)) else None
    financial_sector = not scanner.debt_filter_applies(info)
    health["debt_equity_is_financial"] = financial_sector
    if not financial_sector and equity is not None and equity > 0 and debt is not None:
        health["debt_to_equity"] = round(debt / equity, 2)
        health["debt_equity_display"] = round(debt / equity, 2)
        health["debt_equity_source"] = "balance_sheet" if bs is not None else "quote_summary"
        print(f"    🧮 Debt/Equity: {health['debt_equity_display']:.2f} ({health['debt_equity_source']})")
    elif financial_sector:
        health["debt_equity_display"] = None
        health["debt_equity_source"] = "financial_sector"
    else:
        health["debt_equity_display"] = None
        health["debt_equity_source"] = "unavailable"
        print("    ⚠️ Debt/Equity unavailable: non-financial company but equity/debt data is missing")
    return health


scanner.get_financial_health = get_financial_health_fixed


def _extract_news_item(item):
    if not isinstance(item, dict):
        return None
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    title = item.get("title") or content.get("title")
    publisher = item.get("publisher")
    if not publisher:
        provider = content.get("provider")
        if isinstance(provider, dict):
            publisher = provider.get("displayName")
    link = item.get("link")
    if not link:
        for key in ("canonicalUrl", "clickThroughUrl"):
            candidate = content.get(key)
            if isinstance(candidate, dict):
                link = candidate.get("url")
                if link:
                    break
    pub_date = item.get("providerPublishTime") or content.get("pubDate")
    if isinstance(pub_date, str):
        try:
            pub_date = pd.Timestamp(pub_date).timestamp()
        except Exception:
            pub_date = None
    return {
        "title": str(title).strip() if title else "",
        "publisher": str(publisher).strip() if publisher else "",
        "link": link,
        "timestamp": float(pub_date) if pub_date is not None and str(pub_date) != "nan" else None,
    }


def _normalize_company_tokens(text):
    text = re.sub(r"[^a-z0-9]+", " ", str(text).lower())
    return {token for token in text.split() if len(token) >= 3}


def _headline_matches_company(headline, ticker, company_name):
    title_tokens = _normalize_company_tokens(headline)
    company_tokens = _normalize_company_tokens(company_name)
    ticker_tokens = _normalize_company_tokens(ticker)
    if ticker_tokens & title_tokens:
        return True
    stopwords = {
        "inc", "incorporated", "corp", "corporation", "company", "co", "ltd",
        "limited", "holdings", "group", "plc", "class"
    }
    meaningful = company_tokens - stopwords
    if not meaningful:
        return False
    if len(meaningful) == 1:
        return next(iter(meaningful)) in title_tokens
    return len(meaningful & title_tokens) >= 2


def _news_headlines_from_yahoo(ticker, company_name, max_items=5, max_age_days=30):
    stock = yf.Ticker(ticker)
    raw = stock.news
    if raw is None:
        print(f"    📰 {ticker}: yfinance news returned None")
        return []
    if not isinstance(raw, (list, tuple)):
        print(f"    ⚠️ {ticker}: unexpected yfinance news type: {type(raw).__name__}")
        return []
    print(f"    📰 {ticker}: yfinance returned {len(raw)} news items")
    cutoff = datetime.now().timestamp() - max_age_days * 86400
    parsed = []
    rejected = 0
    for item in raw:
        data = _extract_news_item(item)
        if not data or not data["title"]:
            continue
        ts = data["timestamp"]
        if ts is not None and ts < cutoff:
            continue
        if not _headline_matches_company(data["title"], ticker, company_name):
            rejected += 1
            continue
        headline = data["title"]
        if data["publisher"]:
            headline += f" ({data['publisher']})"
        parsed.append(headline)
        if len(parsed) >= max_items:
            break
    print(f"    📰 {ticker}: parsed {len(parsed)} company-specific headlines; rejected {rejected} unrelated headlines")
    return parsed


def search_recent_news_fixed(ticker, company_name):
    try:
        headlines = _news_headlines_from_yahoo(ticker, company_name)
        if headlines:
            return headlines
        print(f"    📰 {ticker}: no verified company-specific headlines; no cause inferred from price")
        return ["No verified company-specific recent news available — price action only"]
    except Exception as exc:
        print(f"    ❌ {ticker}: news fetch FAILED: {type(exc).__name__}: {exc}")
        return ["No verified company-specific recent news available — price action only"]


scanner.search_recent_news = search_recent_news_fixed


def analyze_price_shape_fixed(stock, current_price):
    empty = {"shape": "insufficient_data", "stable_years": None, "stable_drift_pct": None,
             "stable_range_pct": None, "recent_drop_pct": None, "shape_recent_volatility": None,
             "shape_stable_r2": None}
    try:
        hist = stock.history(period="5y")
        min_days = int(scanner.SHAPE_MIN_STABLE_YEARS * 252) + scanner.SHAPE_RECENT_WINDOW_DAYS
        if hist is None or len(hist) < min_days:
            print("    📐 Shape: insufficient history")
            return empty
        close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
        stable = close.iloc[:-scanner.SHAPE_RECENT_WINDOW_DAYS]
        recent = close.iloc[-scanner.SHAPE_RECENT_WINDOW_DAYS:]
        if len(stable) < int(scanner.SHAPE_MIN_STABLE_YEARS * 252):
            print("    📐 Shape: insufficient stable-period history")
            return empty
        stable_start = float(stable.iloc[:21].mean())
        stable_end = float(stable.iloc[-21:].mean())
        stable_high = float(stable.max())
        stable_low = float(stable.min())
        stable_years = len(stable) / 252.0
        if stable_start <= 0 or stable_high <= 0:
            return empty
        stable_drift = (stable_end / stable_start - 1.0) * 100.0
        stable_range = (stable_high / stable_low - 1.0) * 100.0 if stable_low > 0 else np.inf
        recent_drop = (float(current_price) / stable_high - 1.0) * 100.0
        y = np.log(stable.values)
        x = np.arange(len(y), dtype=float)
        coeff = np.polyfit(x, y, 1)
        slope, intercept = float(coeff[0]), float(coeff[1])
        fitted = slope * x + intercept
        ss_res = float(np.sum((y - fitted) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        annualized_drift = (np.exp(slope * 252.0) - 1.0) * 100.0
        recent_returns = recent.pct_change().dropna()
        recent_vol = float(recent_returns.std() * np.sqrt(252.0) * 100.0) if len(recent_returns) > 2 else None
        gradual = stable_drift <= scanner.SHAPE_GRADUAL_DECLINE_DRIFT_PCT or (annualized_drift <= -10.0 and r2 >= 0.25)
        sudden = recent_drop <= scanner.SHAPE_SUDDEN_DROP_MIN_PCT and not gradual and stable_drift > -25.0
        shape = "gradual_decline" if gradual else "sudden_drop" if sudden else "choppy"
        print(
            f"    📐 Shape signals: drift={stable_drift:.1f}%, annualized_trend={annualized_drift:.1f}%, R²={r2:.2f}, "
            f"range={stable_range:.1f}%, recent_drop={recent_drop:.1f}%, recent_vol={recent_vol:.1f}% -> {shape}"
            if recent_vol is not None else
            f"    📐 Shape signals: drift={stable_drift:.1f}%, annualized_trend={annualized_drift:.1f}%, R²={r2:.2f}, "
            f"range={stable_range:.1f}%, recent_drop={recent_drop:.1f}% -> {shape}"
        )
        return {"shape": shape, "stable_years": stable_years, "stable_drift_pct": stable_drift,
                "stable_range_pct": stable_range, "recent_drop_pct": recent_drop,
                "shape_recent_volatility": recent_vol, "shape_stable_r2": r2}
    except Exception as exc:
        print(f"    ❌ Shape analysis FAILED: {type(exc).__name__}: {exc}")
        return empty


scanner.analyze_price_shape = analyze_price_shape_fixed


_original_generate_email_html = scanner.generate_email_html


def _patch_detail_html(html, stocks):
    for stock in list(stocks or []):
        ticker = re.escape(str(stock.get("ticker", "")))
        health = stock.get("financial_health") or {}
        if health.get("debt_equity_source") == "unavailable":
            pattern = rf"(<h3>{ticker}:.*?</h3>.*?Debt/Equity:) n/a \\(financial sector or unreliable data\\)"
            html = re.sub(pattern, r"\1 n/a (data unavailable)", html, count=1, flags=re.S)
    for stock in list(stocks or []):
        health = stock.get("financial_health") or {}
        if health.get("current_ratio_source") == "unavailable":
            ticker = re.escape(str(stock.get("ticker", "")))
            html = re.sub(rf"(<h3>{ticker}:.*?</h3>.*?Current Ratio:) 0\\.00", r"\1 n/a (data unavailable)", html, count=1, flags=re.S)
    return html


def generate_email_html_fixed(analyzed_stocks, price_alerts, fresh_crash_stocks=None):
    html = _original_generate_email_html(analyzed_stocks, price_alerts, fresh_crash_stocks)
    all_stocks = list(analyzed_stocks or []) + list(fresh_crash_stocks or [])
    return _patch_detail_html(html, all_stocks)


scanner.generate_email_html = generate_email_html_fixed

parse_news_item = _extract_news_item
analyze_price_shape = analyze_price_shape_fixed
get_financial_health = get_financial_health_fixed
