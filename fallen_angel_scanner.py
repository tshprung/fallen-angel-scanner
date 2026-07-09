# fallen_angel_scanner_v2.py
"""
Two-Stage Fallen Angel Scanner with News Analysis
Stage 1: Quick filter for price drops (fast)
Stage 2: Deep analysis only for candidates found (comprehensive)

Goal: names trading well below a plausible “normal” range (heuristics: drawdown,
liquidity, recovery headroom, fundamentals) where the move may be driven by
temporary noise rather than permanent impairment. Biotechnology names are excluded
by sector/industry (binary clinical/regulatory risk, different game than your thesis).

Features:
- News analysis for each candidate
- 14-day deduplication memory
- Earnings calendar check
- Price alerts for averaging down
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import json
import time

from tickers_config import (
    get_all_tickers,
    get_min_market_cap_usd,
    get_min_avg_dollar_volume_usd,
)

# ============================================================================
# RETRY LOGIC FOR RATE LIMITS
# ============================================================================

def get_stock_with_retry(ticker, max_retries=5):
    """Fetch stock data with exponential backoff on rate limits"""
    for attempt in range(max_retries):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            # Verify we got actual data
            if not info or len(info) == 0:
                raise Exception("Empty info returned")
            return stock, info
        except Exception as e:
            error_msg = str(e)
            if "Rate limited" in error_msg or "Too Many Requests" in error_msg:
                wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s, 40s, 80s
                print(f"  ⏸️  Rate limited on attempt {attempt + 1}/{max_retries}, waiting {wait_time}s...")
                time.sleep(wait_time)
                if attempt == max_retries - 1:
                    raise Exception(f"Rate limited after {max_retries} retries")
            else:
                raise e
    return None, None

# ============================================================================
# CONFIGURATION
# ============================================================================

# Email settings
EMAIL_FROM = os.getenv("SENDER_EMAIL")
EMAIL_TO = os.getenv("RECEIVER_EMAIL")
EMAIL_PASSWORD = os.getenv("SENDER_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Scanning criteria
MIN_DROP_PERCENT = 20  # Minimum drop percentage
DROP_LOOKBACK_DAYS = 21  # Look for drops over last 21 days
DROP_FROM_52W_HIGH_MIN = 35  # ~35% below peak → ~54% recovery vs 52w high (clears 50% gate)
MIN_RECOVERY_POTENTIAL_PCT = 50.0  # Require ~50%+ implied upside vs 52-week high
EARNINGS_EXCLUDE_DAYS = 5  # Hard exclude if earnings within this many calendar days
EARNINGS_NOTE_DAYS_MAX = 21  # Informational earnings note up to this many days

# Price shape criteria (sudden-drop fallen angel vs gradual multi-quarter decliner)
SHAPE_MIN_STABLE_YEARS = 2  # Min years of pre-drop history required to judge shape
SHAPE_RECENT_WINDOW_DAYS = 126  # ~6 trading months treated as the "recent drop" window
SHAPE_GRADUAL_DECLINE_DRIFT_PCT = -25  # Stable-period drift below this = already bleeding for years (TTD-pattern) -> hard exclude
SHAPE_SUDDEN_DROP_MIN_PCT = -25  # Min drop from stable-period high to current price to call it "sudden"
SHAPE_MAX_STABLE_RANGE_PCT = 60  # Stable-period high/low range above this = too choppy to call "stable"
MAX_CANDIDATES = 20  # Final report size; if more pass Stage 2, tiers tighten until ≤ this

# Risk filters (operating companies only — see debt_filter_applies)
MAX_DEBT_TO_EQUITY = 2.5  # When Yahoo D/E is trustworthy, exclude above this
DEBT_RATIO_TRUST_MAX = 50.0  # Values above this are usually bad Yahoo data — skip exclusion
NET_DEBT_TO_MCAP_MAX = 1.0  # net debt > 1x market cap = equity stub

# Memory/tracking
MEMORY_FILE = "scanner_memory.json"
DEDUP_DAYS = 14  # Don't re-send same stock within 14 days
PRICE_ALERT_THRESHOLD = 0.10  # Alert if stock drops another 10%

# Ticker validation
FAILED_TICKER_FILE = "failed_tickers.json"
MAX_FAILURES_BEFORE_REMOVAL = 3  # Remove ticker after 3 consecutive failures

# ============================================================================
# MEMORY MANAGEMENT
# ============================================================================

def load_memory():
    """Load scanner memory (sent stocks and their prices)"""
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r') as f:
                return json.load(f)
        return {"sent_stocks": {}, "tracked_prices": {}}
    except:
        return {"sent_stocks": {}, "tracked_prices": {}}

def save_memory(memory):
    """Save scanner memory"""
    try:
        with open(MEMORY_FILE, 'w') as f:
            json.dump(memory, f, indent=2)
    except Exception as e:
        print(f"Failed to save memory: {e}")

def load_failed_tickers():
    """Load failed ticker tracking"""
    try:
        if os.path.exists(FAILED_TICKER_FILE):
            with open(FAILED_TICKER_FILE, 'r') as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_failed_tickers(failed_tickers):
    """Save failed ticker tracking"""
    try:
        with open(FAILED_TICKER_FILE, 'w') as f:
            json.dump(failed_tickers, f, indent=2)
    except Exception as e:
        print(f"Failed to save failed tickers: {e}")

def record_ticker_failure(ticker, failed_tickers, reason):
    """Record a ticker failure. Returns True if ticker should be flagged for removal."""
    if ticker not in failed_tickers:
        failed_tickers[ticker] = {
            "count": 1,
            "last_failure": datetime.now().isoformat(),
            "reason": reason
        }
    else:
        failed_tickers[ticker]["count"] += 1
        failed_tickers[ticker]["last_failure"] = datetime.now().isoformat()
        failed_tickers[ticker]["reason"] = reason
    
    return failed_tickers[ticker]["count"] >= MAX_FAILURES_BEFORE_REMOVAL

def record_ticker_success(ticker, failed_tickers):
    """Remove ticker from failed list if it succeeds"""
    if ticker in failed_tickers:
        del failed_tickers[ticker]

def should_send_stock(ticker, memory):
    """Check if stock was already sent recently"""
    sent_stocks = memory.get("sent_stocks", {})
    if ticker in sent_stocks:
        last_sent = datetime.fromisoformat(sent_stocks[ticker])
        if (datetime.now() - last_sent).days < DEDUP_DAYS:
            print(f"  ⏭️  {ticker} sent {(datetime.now() - last_sent).days} days ago, skipping")
            return False
    return True

def check_price_alerts(memory):
    """Check if any tracked stocks dropped significantly for averaging down"""
    alerts = []
    tracked = memory.get("tracked_prices", {})
    
    for ticker, data in tracked.items():
        try:
            stock = yf.Ticker(ticker)
            current_price = stock.history(period="1d")["Close"].iloc[-1].item()
            original_price = data["price"]
            stored_date = data.get("date")

            # Adjust for splits that occurred after the stored date
            try:
                splits = stock.splits
                if stored_date and splits is not None and not splits.empty:
                    split_cutoff = pd.Timestamp(stored_date).tz_localize("UTC")
                    splits.index = splits.index.tz_convert("UTC")
                    recent_splits = splits[splits.index > split_cutoff]
                    if not recent_splits.empty:
                        cumulative_ratio = recent_splits.prod().item()
                        original_price = original_price / cumulative_ratio
            except Exception:
                pass

            drop_since_alert = (current_price / original_price - 1)
            
            if drop_since_alert <= -PRICE_ALERT_THRESHOLD:
                alerts.append({
                    'ticker': ticker,
                    'original_price': original_price,
                    'current_price': current_price,
                    'additional_drop': drop_since_alert * 100,
                    'sent_date': data['date']
                })
        except Exception as e:
            print(f"  ⚠️  Failed to check {ticker}: {e}")
            continue
    
    return alerts

# ============================================================================
# MARKET HELPERS
# ============================================================================

def get_market_info(ticker):
    """Determine market and currency from ticker"""
    if ticker.endswith('.WA'):
        return "🇵🇱 Poland", "PLN"
    elif ticker.endswith('.L'):
        return "🇬🇧 UK", "GBP"
    elif ticker.endswith('.TA'):
        return "🇮🇱 Israel", "ILS"
    elif ticker.endswith('.DE'):
        return "🇩🇪 Germany", "EUR"
    else:
        return "🇺🇸 US", "USD"

def format_price_for_email(price, currency_code):
    """Prefix/suffix by currency for email (avoid showing USD $ for PLN/GBP etc.)."""
    c = (currency_code or "USD").upper()
    if c == "GBP":
        return f"£{price:.2f}"
    if c == "EUR":
        return f"€{price:.2f}"
    if c == "PLN":
        return f"{price:.2f} zł"
    if c == "ILS":
        return f"₪{price:.2f}"
    return f"${price:.2f}"


def format_cash_billions_for_email(cash, currency_code):
    """Format cash balance in billions with correct currency symbol."""
    if cash is None:
        return "n/a"
    try:
        b = float(cash) / 1e9
        if not np.isfinite(b):
            return "n/a"
    except (TypeError, ValueError):
        return "n/a"
    c = (currency_code or "USD").upper()
    if c == "GBP":
        return f"£{b:.2f}B"
    if c == "EUR":
        return f"€{b:.2f}B"
    if c == "PLN":
        return f"{b:.2f}B zł"
    if c == "ILS":
        return f"₪{b:.2f}B"
    return f"${b:.2f}B"


def format_rsi_for_email(rsi):
    """RSI display with color icon: green <35, yellow 35-50, red >50."""
    if rsi is None or not np.isfinite(float(rsi)):
        return "n/a"
    r = float(rsi)
    if r < 35:
        icon = "🟢"
    elif r <= 50:
        icon = "🟡"
    else:
        icon = "🔴"
    return f"{icon} {r:.1f}"


def compute_rsi(closes, period=14):
    """Wilder-style RSI from close series; None if insufficient data."""
    if closes is None or len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    if val is None or pd.isna(val) or not np.isfinite(float(val)):
        return None
    return float(val)


def is_tradeable_equity(info):
    """Skip ETFs/funds and OTC names — focus on listed operating equities."""
    qt = (info.get("quoteType") or "").upper()
    if qt in ("ETF", "MUTUALFUND", "INDEX", "ETN", "CRYPTOCURRENCY"):
        return False
    ex = ((info.get("exchange") or "") + " " + (info.get("fullExchangeName") or "")).upper()
    if "OTC" in ex or "PINK" in ex or "OTCBB" in ex:
        return False
    return True


def not_penny_delist_risk(info, ticker):
    """Avoid ultra-low-priced names where delisting is more common."""
    p = info.get("regularMarketPrice") or info.get("currentPrice")
    if p is None or p <= 0:
        return True
    if ticker.endswith(".WA") or ticker.endswith(".TA") or ticker.endswith(".L") or ticker.endswith(".DE"):
        return p >= 1.0
    return p >= 2.0


def passes_avg_dollar_liquidity(hist, min_dollar_vol_usd):
    """20-day average dollar volume (uses last N rows of history)."""
    if hist is None or len(hist) < 10:
        return False
    tail = hist.tail(min(20, len(hist)))
    dv = (tail["Close"] * tail["Volume"]).mean()
    return dv >= min_dollar_vol_usd


def debt_filter_applies(info):
    """
    Debt/equity from Yahoo is meaningless for banks/insurers/REITs and often broken
    for other names. Only apply the leverage exclusion to operating companies.
    """
    sector = (info.get("sector") or "").strip().lower()
    industry = (info.get("industry") or "").strip().lower()
    if sector in ("financial services", "real estate"):
        return False
    needles = (
        "bank",
        "insurance",
        "reit",
        "capital market",
        "asset management",
        "credit services",
        "mortgage",
        "financial -",
        "consumer - financial",
        "investment - financial",
        "regional -",
        "shell company",
    )
    if any(n in industry for n in needles):
        return False
    return True


def compute_debt_to_equity_ratio(info):
    """Single place for D/E used by Stage 2 and financial health. None if unknown."""
    total_debt = info.get("totalDebt", 0) or 0
    total_equity = info.get("totalStockholderEquity")
    if total_equity is not None and total_equity > 0:
        return total_debt / total_equity
    de_yf = info.get("debtToEquity")
    if de_yf is not None and np.isfinite(float(de_yf)):
        return float(de_yf)
    return None


def should_exclude_for_leverage(info):
    """
    Exclude for high leverage only when ratio is present, sane, and sector is comparable.
    Returns (exclude: bool, reason or None).
    """
    if not debt_filter_applies(info):
        return False, None

    total_debt = info.get("totalDebt", 0) or 0
    total_equity = info.get("totalStockholderEquity")
    de = compute_debt_to_equity_ratio(info)

    if (
        total_equity is not None
        and total_equity < 0
        and total_debt > 0
        and de is None
    ):
        return True, "Negative book equity with debt (high risk)"

    if de is None:
        return False, None
    if de > DEBT_RATIO_TRUST_MAX:
        return False, None
    if de > MAX_DEBT_TO_EQUITY:
        return True, f"High debt (D/E: {de:.2f})"

    # Equity stub gate: net debt exceeds market cap
    market_cap = info.get("marketCap", 0) or 0
    total_cash_for_stub = info.get("totalCash", 0) or 0
    net_debt_for_stub = total_debt - total_cash_for_stub
    if (
        market_cap > 0
        and net_debt_for_stub > 0
        and (net_debt_for_stub / market_cap) >= NET_DEBT_TO_MCAP_MAX
    ):
        ratio = net_debt_for_stub / market_cap
        return True, f"Equity stub: net debt {ratio:.1f}x market cap"

    return False, None


BIOTECH_EXCLUSION_KEYWORDS = (
    "biotechnology",
    "pharmaceutical",
    "drug manufacturer",
    "clinical stage",
    "biopharmaceutical",
)


def is_biotechnology_company(info):
    """
    Exclude biotech/pharma/clinical-stage names (not med devices or diagnostics).
    """
    ind = f"{info.get('industry') or ''} {info.get('industryKey') or ''}".lower()
    return any(kw in ind for kw in BIOTECH_EXCLUSION_KEYWORDS)


def profitability_signals(info):
    """
    Count negative profitability flags and whether all three trigger hard exclude.
    Uses Yahoo defaults when fields are missing (same as gate spec).
    """
    neg_gm = info.get("grossMargins", 1) < 0
    neg_ocf = info.get("operatingCashflow", 1) < 0
    neg_rg = info.get("revenueGrowth", 0) < -0.10
    n_neg = sum((neg_gm, neg_ocf, neg_rg))
    hard_exclude = neg_gm and neg_ocf and neg_rg
    return n_neg, hard_exclude


def compute_piotroski_score(info, ticker_obj):
    score = 0
    checked = 0

    try:
        fin = ticker_obj.financials
        bs = ticker_obj.balance_sheet
    except Exception:
        fin, bs = None, None

    def get_row(df, *keys):
        if df is None or df.empty:
            return None
        for k in keys:
            if k in df.index:
                return df.loc[k]
        return None

    def val(series, idx):
        try:
            v = series.iloc[idx]
            return float(v) if v is not None and not pd.isna(v) else None
        except Exception:
            return None

    ni = info.get('netIncomeToCommon')
    ta = info.get('totalAssets')
    ocf = info.get('operatingCashflow')

    # F1: ROA > 0
    if ni is not None and ta and ta > 0:
        checked += 1
        if ni / ta > 0:
            score += 1

    # F2: OCF > 0
    if ocf is not None:
        checked += 1
        if ocf > 0:
            score += 1

    # F3: ROA improving YoY
    ni_row = get_row(fin, 'Net Income', 'Net Income Common Stockholders')
    ta_row = get_row(bs, 'Total Assets')
    if ni_row is not None and ta_row is not None:
        ni0, ni1 = val(ni_row, 0), val(ni_row, 1)
        ta0, ta1 = val(ta_row, 0), val(ta_row, 1)
        if all(v is not None and v != 0 for v in [ni0, ni1, ta0, ta1]):
            checked += 1
            if ni0 / ta0 > ni1 / ta1:
                score += 1

    # F4: Accruals — OCF/Assets > ROA
    if ocf is not None and ta and ta > 0 and ni is not None:
        checked += 1
        if (ocf / ta) > (ni / ta):
            score += 1

    # F5: Long-term leverage decreased YoY
    ltd_row = get_row(bs, 'Long Term Debt', 'Long-Term Debt')
    if ltd_row is not None and ta_row is not None:
        ltd0, ltd1 = val(ltd_row, 0), val(ltd_row, 1)
        ta0, ta1 = val(ta_row, 0), val(ta_row, 1)
        if all(v is not None for v in [ltd0, ltd1, ta0, ta1]) and ta0 > 0 and ta1 > 0:
            checked += 1
            if ltd0 / ta0 < ltd1 / ta1:
                score += 1

    # F6: Current ratio improved YoY
    ca_row = get_row(bs, 'Current Assets')
    cl_row = get_row(bs, 'Current Liabilities')
    if ca_row is not None and cl_row is not None:
        ca0, ca1 = val(ca_row, 0), val(ca_row, 1)
        cl0, cl1 = val(cl_row, 0), val(cl_row, 1)
        if all(v is not None for v in [ca0, ca1, cl0, cl1]) and cl0 > 0 and cl1 > 0:
            checked += 1
            if ca0 / cl0 > ca1 / cl1:
                score += 1

    # F7: No new share dilution (allow 2% tolerance)
    sh_row = get_row(
        bs,
        'Ordinary Shares Number',
        'Share Issued',
        'Common Stock Shares Outstanding',
    )
    if sh_row is not None:
        sh0, sh1 = val(sh_row, 0), val(sh_row, 1)
        if sh0 is not None and sh1 is not None:
            checked += 1
            if sh0 <= sh1 * 1.02:
                score += 1

    # F8: Gross margin improved YoY
    gp_row = get_row(fin, 'Gross Profit')
    rev_row = get_row(fin, 'Total Revenue')
    if gp_row is not None and rev_row is not None:
        gp0, gp1 = val(gp_row, 0), val(gp_row, 1)
        rv0, rv1 = val(rev_row, 0), val(rev_row, 1)
        if all(v is not None and v != 0 for v in [gp0, gp1, rv0, rv1]):
            checked += 1
            if gp0 / rv0 > gp1 / rv1:
                score += 1

    # F9: Asset turnover improved YoY
    if rev_row is not None and ta_row is not None:
        rv0, rv1 = val(rev_row, 0), val(rev_row, 1)
        ta0, ta1 = val(ta_row, 0), val(ta_row, 1)
        if all(v is not None for v in [rv0, rv1, ta0, ta1]) and ta0 > 0 and ta1 > 0:
            checked += 1
            if rv0 / ta0 > rv1 / ta1:
                score += 1

    if checked < 5:
        return None, checked
    return score, checked


def format_piotroski_for_email(score, checks):
    """Piotroski display: F:7/9 ⭐ when score >= 7."""
    if score is None or checks is None:
        return "F:n/a"
    star = " ⭐" if score >= 7 else ""
    return f"F:{score}/{checks}{star}"


def format_shape_for_email(price_shape, stable_years, recent_drop_pct):
    """Price shape display: sudden drop vs choppy vs limited history."""
    if price_shape == "sudden_drop":
        years_txt = f"{stable_years:.1f}y" if stable_years is not None else "?"
        drop_txt = (
            f"{recent_drop_pct:.0f}%"
            if recent_drop_pct is not None and np.isfinite(recent_drop_pct)
            else "?"
        )
        return f"🎯 Sudden drop (stable {years_txt}, then {drop_txt})"
    elif price_shape == "choppy":
        return "〰️ Mixed/choppy"
    elif price_shape == "insufficient_data":
        return "❓ Limited history"
    return "—"


def narrow_analyzed_results(analyzed, max_results=20):
    """
    If Stage 2 yields more than max_results, apply progressively stricter cuts
    (lower risk score, higher recovery bar) until the list fits.
    """
    if len(analyzed) <= max_results:
        return sorted(
            analyzed, key=lambda x: (x["risk_score"], -x["recovery_potential"])
        )

    n_before = len(analyzed)
    pool = sorted(analyzed, key=lambda x: (x["risk_score"], -x["recovery_potential"]))

    steps = [
        ("risk ≤ 5", lambda s: s["risk_score"] <= 5),
        ("risk ≤ 4", lambda s: s["risk_score"] <= 4),
        ("risk ≤ 4 & recovery ≥ 55%", lambda s: s["risk_score"] <= 4 and s["recovery_potential"] >= 55),
        ("risk ≤ 4 & recovery ≥ 60%", lambda s: s["risk_score"] <= 4 and s["recovery_potential"] >= 60),
        ("risk ≤ 3", lambda s: s["risk_score"] <= 3),
        ("risk ≤ 3 & recovery ≥ 58%", lambda s: s["risk_score"] <= 3 and s["recovery_potential"] >= 58),
        ("risk ≤ 2", lambda s: s["risk_score"] <= 2),
    ]

    last_non_empty = pool
    for label, pred in steps:
        filt = [s for s in pool if pred(s)]
        if not filt:
            continue
        last_non_empty = sorted(filt, key=lambda x: (x["risk_score"], -x["recovery_potential"]))
        if len(last_non_empty) <= max_results:
            print(
                f"  📉 Tightened selection ({n_before} → {len(last_non_empty)}): {label}"
            )
            return last_non_empty

    out = last_non_empty[:max_results]
    print(
        f"  📉 Tightened selection ({n_before} → {len(out)}): top {max_results} by risk / recovery"
    )
    return out


def get_broker_recommendation(market):
    """Recommend broker based on market"""
    brokers = {
        "🇺🇸 US": "📱 Revolut",
        "🇵🇱 Poland": "🏦 mBank eMakler",
        "🇬🇧 UK": "🏦 mBank eMakler",
        "🇩🇪 Germany": "🏦 mBank eMakler",
        "🇮🇱 Israel": "🏦 Bank Leumi"
    }
    alternatives = {
        "🇺🇸 US": "or mBank eMakler",
        "🇬🇧 UK": "or Revolut"
    }
    return brokers.get(market, "❓"), alternatives.get(market, "")

# ============================================================================
# STAGE 1: QUICK FILTER
# ============================================================================

def stage1_quick_filter():
    """Stage 1: Fast price/market cap filter to find candidates"""
    print("="*80)
    print("STAGE 1: Quick Price Drop Filter")
    print("="*80)
    
    all_tickers = get_all_tickers()
    failed_tickers = load_failed_tickers()
    
    print(f"Scanning {len(all_tickers)} stocks across 5 markets")
    if failed_tickers:
        print(f"  ⚠️  Tracking {len(failed_tickers)} tickers with failures\n")
    else:
        print()
    
    candidates = []
    tickers_to_remove = []
    
    for i, ticker in enumerate(all_tickers):
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(all_tickers)}")
        
        try:
            stock, info = get_stock_with_retry(ticker)
            if not stock or not info:
                # Record failure
                should_remove = record_ticker_failure(ticker, failed_tickers, "Failed to fetch data")
                if should_remove:
                    tickers_to_remove.append(ticker)
                    print(f"  ❌ {ticker} flagged for removal (3+ failures)")
                continue
            
            # Success - clear from failed list
            record_ticker_success(ticker, failed_tickers)
            
            # Quick checks only
            market_cap = info.get('marketCap', 0) or 0

            if not is_tradeable_equity(info):
                continue
            if not not_penny_delist_risk(info, ticker):
                continue
            if is_biotechnology_company(info):
                continue

            min_cap = get_min_market_cap_usd(ticker)
            if market_cap < min_cap:
                continue
            
            # Get price history
            hist = stock.history(period="1mo")
            if len(hist) < 10:
                continue

            if not passes_avg_dollar_liquidity(hist, get_min_avg_dollar_volume_usd(ticker)):
                continue
            
            current_price = hist["Close"].iloc[-1].item()
            lookback_price = hist["Close"].iloc[-min(DROP_LOOKBACK_DAYS, len(hist))].item()
            drop_21d_pct = ((current_price - lookback_price) / lookback_price) * 100

            if drop_21d_pct <= -MIN_DROP_PERCENT:
                candidates.append({
                    "ticker": ticker,
                    "current_price": current_price,
                    "drop_21d_pct": drop_21d_pct,
                    "market_cap": market_cap,
                })
                print(f"  ✓ {ticker}: {drop_21d_pct:.1f}%")
        
        except Exception as e:
            # Record failure for any exception
            error_msg = str(e)
            if "404" in error_msg or "Not Found" in error_msg:
                should_remove = record_ticker_failure(ticker, failed_tickers, "Ticker not found (404)")
                if should_remove:
                    tickers_to_remove.append(ticker)
                    print(f"  ❌ {ticker} flagged for removal (3+ failures)")
            continue
    
    # Save failed ticker tracking
    save_failed_tickers(failed_tickers)
    
    print(f"\n✅ Stage 1 complete: Found {len(candidates)} candidates")
    if tickers_to_remove:
        print(f"⚠️  {len(tickers_to_remove)} tickers flagged for removal: {', '.join(tickers_to_remove[:10])}")
        if len(tickers_to_remove) > 10:
            print(f"   ... and {len(tickers_to_remove) - 10} more")
    print()
    
    return candidates, tickers_to_remove

# ============================================================================
# STAGE 2: DEEP ANALYSIS
# ============================================================================

def get_earnings_date(ticker):
    try:
        stock = yf.Ticker(ticker)
        calendar = stock.calendar
        if calendar is None:
            return None, None

        # yfinance 0.2.x returns a dict; older versions return a DataFrame
        if isinstance(calendar, dict):
            dates = calendar.get("Earnings Date")
            if not dates:
                return None, None
            earnings_ts = pd.Timestamp(dates[0] if isinstance(dates, list) else dates)
        else:
            if "Earnings Date" not in calendar.index:
                return None, None
            earnings_ts = pd.Timestamp(calendar.loc["Earnings Date"].values[0])

        earnings_ts = earnings_ts.tz_localize(None) if earnings_ts.tzinfo else earnings_ts
        days_until = (earnings_ts.date() - datetime.now().date()).days

        if 0 <= days_until <= EARNINGS_NOTE_DAYS_MAX:
            return earnings_ts.strftime("%Y-%m-%d"), days_until
        return None, None
    except Exception:
        return None, None

def search_recent_news(ticker, company_name):
    """Search for recent news about the stock"""
    try:
        # Try yfinance news first
        stock = yf.Ticker(ticker)
        news_items = stock.news[:5] if hasattr(stock, 'news') and stock.news else []
        
        if news_items:
            headlines = []
            for item in news_items:
                title = item.get('title', '')
                publisher = item.get('publisher', '')
                if title:
                    headlines.append(f"{title} ({publisher})")
            
            if headlines:
                return headlines
        
        # If yfinance fails, try to infer from recent price action
        # This is more reliable than trying external APIs in GitHub Actions
        print(f"    📰 No yfinance news for {ticker}, using price analysis")
        
        # Analyze recent drops to infer cause
        hist = stock.history(period="1mo")
        if len(hist) >= 5:
            # Check if drop is sudden (1-3 days) or gradual
            recent_5d = hist["Close"].tail(5)
            max_recent = recent_5d.max()
            current = recent_5d.iloc[-1]
            drop_5d = ((current / max_recent) - 1) * 100
            
            if drop_5d < -15:
                return ["Sharp drop detected - likely earnings miss, guidance cut, or sector selloff"]
            elif drop_5d < -10:
                return ["Moderate decline - possibly analyst downgrade or sector weakness"]
            else:
                return ["Gradual decline - check for sector trends or market rotation"]
        
        return ["Price decline detected - check recent earnings and sector news"]
    
    except Exception as e:
        print(f"    ⚠️ News search error: {e}")
        return ["Unable to determine cause - manual research needed"]

def analyze_news_sentiment(headlines):
    """Analyze if drop is from temporary noise or real problems"""
    # Keywords indicating temporary issues
    temporary_keywords = [
        'guidance', 'miss', 'earnings', 'outlook', 'forecast', 
        'downgrade', 'analyst', 'sector', 'market', 'selloff',
        'valuation', 'profit-taking', 'rotation'
    ]
    
    # Keywords indicating serious problems
    serious_keywords = [
        'fraud', 'lawsuit', 'investigation', 'scandal', 'bankruptcy',
        'delisting', 'default', 'layoff', 'restructur', 'closure',
        'recall', 'criminal', 'sec inquiry'
    ]
    
    news_text = ' '.join(headlines).lower()
    
    temp_count = sum(1 for kw in temporary_keywords if kw in news_text)
    serious_count = sum(1 for kw in serious_keywords if kw in news_text)
    
    if serious_count > 0:
        return "🔴 SERIOUS ISSUE", "Fundamental problem detected"
    elif temp_count > 0:
        return "🟢 TEMPORARY NOISE", "Likely earnings/guidance miss or sector rotation"
    else:
        return "🟡 UNCLEAR", "Need manual research"

def get_financial_health(ticker_obj):
    """Assess bankruptcy risk from financials (D/E skipped for financials / bad Yahoo data)."""
    try:
        info = ticker_obj.info

        if not debt_filter_applies(info):
            de_for_risk = 0.5
            de_display = None
        else:
            raw = compute_debt_to_equity_ratio(info)
            if raw is None or raw > DEBT_RATIO_TRUST_MAX:
                de_for_risk = 0.5
                de_display = None
            else:
                de_for_risk = float(raw)
                de_display = round(raw, 2)

        current_assets = info.get('totalCurrentAssets', 0) or 0
        current_liabilities = info.get('totalCurrentLiabilities', 0) or 0

        if current_liabilities > 0:
            current_ratio = current_assets / current_liabilities
        else:
            current_ratio = 99 if current_assets > 0 else 0

        cash = info.get('totalCash', 0) or 0
        revenue = info.get('totalRevenue', 0) or 0
        market_cap = info.get('marketCap', 0) or 0

        total_debt = info.get('totalDebt', 0) or 0
        ebitda = info.get('ebitda')
        net_debt = total_debt - cash
        debt_ebitda = None
        if ebitda and np.isfinite(float(ebitda)) and float(ebitda) > 0:
            debt_ebitda = round(total_debt / float(ebitda), 2)

        if de_for_risk > 100:
            de_for_risk = 10.0

        revenue_growth_yoy = None
        try:
            fin = ticker_obj.financials
            if fin is not None and not fin.empty:
                rev_label = None
                for label in fin.index:
                    if str(label).strip().lower() == "total revenue":
                        rev_label = label
                        break
                if rev_label is not None:
                    rev_series = fin.loc[rev_label].dropna()
                    if len(rev_series) >= 2:
                        cols = sorted(rev_series.index, reverse=True)[:2]
                        newer, older = cols[0], cols[1]
                        r_new = float(rev_series[newer])
                        r_old = float(rev_series[older])
                        if r_old != 0 and np.isfinite(r_new) and np.isfinite(r_old):
                            revenue_growth_yoy = ((r_new / r_old) - 1) * 100
        except Exception:
            pass

        return {
            'debt_to_equity': round(de_for_risk, 2),
            'debt_equity_display': de_display,
            'current_ratio': round(current_ratio, 2),
            'cash': cash,
            'revenue': revenue,
            'market_cap': market_cap,
            'revenue_growth_yoy': revenue_growth_yoy,
            'total_debt': total_debt,
            'net_debt': net_debt,
            'debt_ebitda': debt_ebitda,
        }
    except Exception as e:
        print(f"    ⚠️ Financial data error: {e}")
        return None

def calculate_risk_score(
    financial_health,
    news_sentiment,
    rsi=None,
    profitability_penalty=0,
    is_dropping=False,
    piotroski=None,
    market_cap_usd=None,
    debt_ebitda=None,
):
    """Calculate risk score 1-10"""
    if not financial_health:
        return 7  # Default to medium-high if no data
    
    score = 5  # Start neutral
    score += profitability_penalty

    if piotroski is not None:
        if piotroski >= 7:
            score -= 2
        elif piotroski >= 5:
            score -= 1
        elif piotroski <= 2:
            score += 3
        elif piotroski <= 3:
            score += 2

    if market_cap_usd is not None and market_cap_usd > 0:
        cap = float(market_cap_usd)
        if 1_000_000_000 <= cap <= 8_000_000_000:
            score -= 1
        elif cap > 50_000_000_000:
            score += 1
        elif cap < 500_000_000:
            score += 1
    
    # Debt analysis (more nuanced)
    de_ratio = financial_health.get('debt_to_equity', 0)
    if de_ratio < 0.3:
        score -= 2  # Very low debt = safer
    elif de_ratio < 0.7:
        score -= 1  # Moderate debt = good
    elif de_ratio > 2.0:
        score += 3  # High leverage = risky
    elif de_ratio > 1.0:
        score += 1  # Elevated debt

    # Debt/EBITDA — catches high leverage even when D/E looks acceptable
    if debt_ebitda is not None and np.isfinite(float(debt_ebitda)):
        deb = float(debt_ebitda)
        if deb > 5:
            score += 2
        elif deb > 3:
            score += 1
    
    # Liquidity (more forgiving)
    cr = financial_health.get('current_ratio', 0)
    if cr > 2.0:
        score -= 1.5  # Strong liquidity
    elif cr > 1.5:
        score -= 0.5  # Adequate liquidity
    elif cr < 1.0 and cr > 0:
        score += 1  # Weak liquidity
    
    # Revenue check
    revenue = financial_health.get('revenue', 0)
    if revenue == 0:
        score += 2  # No revenue = speculative

    rev_yoy = financial_health.get("revenue_growth_yoy")
    if rev_yoy is not None and np.isfinite(float(rev_yoy)):
        rev_yoy = float(rev_yoy)
        if rev_yoy < -15:
            score += 2
        elif rev_yoy < 0:
            score += 1
        elif rev_yoy > 10:
            score -= 1

    # RSI (Stage 2)
    if rsi is not None and np.isfinite(float(rsi)):
        rsi_f = float(rsi)
        if rsi_f < 35:
            score -= 1
        elif rsi_f > 60 and is_dropping:
            score += 1
    
    # Cash position
    cash = financial_health.get('cash', 0)
    market_cap = financial_health.get('market_cap', 1)
    if market_cap > 0:
        cash_ratio = cash / market_cap
        if cash_ratio > 0.20:
            score -= 1  # Strong cash position
    
    # News sentiment (significant weight)
    if "SERIOUS" in news_sentiment:
        score += 3
    elif "TEMPORARY" in news_sentiment:
        score -= 1.5  # Bigger discount for temporary issues
    
    return max(1, min(10, round(score)))

def check_bankruptcy_risk(stock, info, financial_health):
    """
    Check for bankruptcy risk. Returns (has_risk: bool, reason: str)
    AUTO-EXCLUDE if any critical indicator fails
    """
    try:
        if not financial_health:
            return True, "No financial data available"
        
        # 1. Interest coverage ratio (EBIT / interest expense)
        ebit = info.get('ebit', 0) or 0
        interest_expense = info.get('interestExpense', 0) or 0
        
        if interest_expense > 0:
            interest_coverage = ebit / abs(interest_expense)
            if interest_coverage < 2.0:
                return True, f"Low interest coverage: {interest_coverage:.1f}x (need >2x)"
        elif interest_expense < 0 and ebit < abs(interest_expense) * 2:
            # Handle negative interest expense reporting
            return True, f"Insufficient earnings to cover interest"
        
        # 2. Quick ratio (liquid assets / current liabilities)
        current_assets = info.get('totalCurrentAssets', 0) or 0
        inventory = info.get('inventory', 0) or 0
        current_liabilities = info.get('totalCurrentLiabilities', 0) or 0
        
        if current_liabilities > 0:
            quick_ratio = (current_assets - inventory) / current_liabilities
            if quick_ratio < 0.5:
                return True, f"Low quick ratio: {quick_ratio:.2f} (need >0.5)"
        
        # 3. Operating cash flow must be positive
        cash_flow = stock.cashflow
        if not cash_flow.empty and 'Operating Cash Flow' in cash_flow.index:
            latest_ocf = cash_flow.loc['Operating Cash Flow'].iloc[0]
            if pd.notna(latest_ocf) and latest_ocf < 0:
                return True, "Negative operating cash flow"
        
        # 4. Check for negative equity (bankruptcy indicator)
        total_equity = info.get('totalStockholderEquity', 0)
        if total_equity and total_equity < 0:
            return True, "Negative shareholder equity"
        
        return False, None
        
    except Exception as e:
        print(f"    ⚠️ Bankruptcy check error: {e}")
        return True, f"Unable to verify financial stability: {e}"

def detect_bottom(stock, current_price):
    """
    Technical analysis to detect if stock is at bottom.
    Returns: (at_bottom: bool, wait_price_low: float, wait_price_high: float, confidence: str)
    """
    try:
        hist = stock.history(period="1y")
        if len(hist) < 50:
            return False, None, None, "Insufficient data"
        
        # Calculate indicators
        close = hist['Close']
        
        # 1. RSI (14-day)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = float(rsi.iloc[-1].item())
        
        # 2. 52-week low
        week_52_low = close.min().item()
        distance_from_low = ((current_price - week_52_low) / week_52_low) * 100
        
        # 3. Bollinger Bands (20-day)
        sma_20 = close.rolling(window=20).mean()
        std_20 = close.rolling(window=20).std()
        lower_band = sma_20 - (2 * std_20)
        current_lower_band = lower_band.iloc[-1].item()
        
        # 4. Volume trend (selling exhaustion?)
        volume = hist['Volume']
        avg_volume_20 = volume.rolling(window=20).mean()
        recent_volume = volume.iloc[-5:].mean()  # Last 5 days
        volume_declining = recent_volume.item() < avg_volume_20.iloc[-1].item() * 0.8
        
        # 5. Find support levels (previous lows in last year)
        support_levels = []
        for i in range(10, len(close) - 10):
            if close.iloc[i].item() == close.iloc[i-10:i+10].min().item():
                support_levels.append(close.iloc[i].item())
        
        nearest_support = None
        if support_levels:
            support_below = [s for s in support_levels if s < current_price]
            if support_below:
                nearest_support = max(support_below)
        
        # Decision logic
        at_bottom = False
        confidence = "LOW"
        
        if current_rsi < 30 and distance_from_low < 15:
            # Oversold + near 52-week low
            at_bottom = True
            confidence = "HIGH"
        elif current_rsi < 35 and distance_from_low < 20 and volume_declining:
            # Moderately oversold + near low + volume declining
            at_bottom = True
            confidence = "MEDIUM"
        elif current_price <= current_lower_band * 1.02:
            # At or just above lower Bollinger Band
            at_bottom = True
            confidence = "MEDIUM"
        
        # Calculate wait price if NOT at bottom
        wait_price_low = None
        wait_price_high = None
        
        if not at_bottom:
            # Estimate bottom using: min(52-week low, nearest support, lower Bollinger band)
            candidates = [week_52_low]
            if nearest_support:
                candidates.append(nearest_support)
            if current_lower_band > 0:
                candidates.append(current_lower_band)
            
            estimated_bottom = min(candidates)
            wait_price_low = estimated_bottom * 0.95  # -5%
            wait_price_high = estimated_bottom * 1.05  # +5%
        
        return at_bottom, wait_price_low, wait_price_high, confidence
        
    except Exception as e:
        print(f"    ⚠️ Technical analysis error: {e}")
        return False, None, None, "Error"

def analyze_price_shape(stock, current_price):
    """
    Classify the shape of a stock's price history to distinguish sudden-drop
    fallen angels (e.g. ACN: stable for years, dropped this year on a single
    catalyst) from gradual multi-quarter decliners (e.g. TTD: eroding steadily
    over many quarters, no single break).

    Splits history into a "stable period" (everything except the last
    SHAPE_RECENT_WINDOW_DAYS) and a "recent period" (the last window), then
    checks whether the stable period was actually stable (flat-to-up, low
    volatility) before a sharp recent break.

    Returns dict:
        shape: "sudden_drop" | "gradual_decline" | "choppy" | "insufficient_data"
        stable_years: float or None
        stable_drift_pct: float or None  (long-term trend during stable years)
        stable_range_pct: float or None  (high/low volatility during stable years)
        recent_drop_pct: float or None   (drop from stable-period high to current price)
    """
    empty_result = {
        "shape": "insufficient_data",
        "stable_years": None,
        "stable_drift_pct": None,
        "stable_range_pct": None,
        "recent_drop_pct": None,
    }
    try:
        hist = stock.history(period="5y")
        min_days_needed = int(SHAPE_MIN_STABLE_YEARS * 252) + SHAPE_RECENT_WINDOW_DAYS

        if hist is None or len(hist) < min_days_needed:
            return empty_result

        close = hist["Close"]
        stable = close.iloc[:-SHAPE_RECENT_WINDOW_DAYS]

        if len(stable) < int(SHAPE_MIN_STABLE_YEARS * 252):
            return empty_result

        stable_start = stable.iloc[:21].mean().item()
        stable_end = stable.iloc[-21:].mean().item()
        stable_high = stable.max().item()
        stable_low = stable.min().item()
        stable_years = len(stable) / 252

        if stable_start <= 0 or stable_high <= 0:
            result = dict(empty_result)
            result["stable_years"] = stable_years
            return result

        stable_drift_pct = ((stable_end - stable_start) / stable_start) * 100
        stable_range_pct = ((stable_high - stable_low) / stable_high) * 100
        recent_drop_pct = ((current_price - stable_high) / stable_high) * 100

        if stable_drift_pct <= SHAPE_GRADUAL_DECLINE_DRIFT_PCT:
            # Already bleeding for years before the "recent" window even
            # starts -> TTD-pattern, not a fallen angel.
            shape = "gradual_decline"
        elif (
            stable_range_pct <= SHAPE_MAX_STABLE_RANGE_PCT
            and recent_drop_pct <= SHAPE_SUDDEN_DROP_MIN_PCT
        ):
            shape = "sudden_drop"
        else:
            shape = "choppy"

        return {
            "shape": shape,
            "stable_years": stable_years,
            "stable_drift_pct": stable_drift_pct,
            "stable_range_pct": stable_range_pct,
            "recent_drop_pct": recent_drop_pct,
        }

    except Exception as e:
        print(f"    ⚠️ Shape analysis error: {e}")
        return empty_result

def estimate_recovery_target(stock, info, current_price):
    """
    Estimate realistic recovery price target.
    Returns: (target_low: float, target_high: float, upside_pct: float)
    """
    try:
        hist = stock.history(period="5y")
        if len(hist) < 250:
            hist = stock.history(period="1y")
        
        # Method 1: Historical valuation (5-year average P/E)
        pe_ratio = info.get('trailingPE', 0) or 0
        eps = info.get('trailingEps', 0) or 0
        
        target_from_pe = None
        if hist is not None and len(hist) > 250:
            # Calculate historical average price
            avg_price_5y = hist['Close'].mean()
            high_80pct = hist['Close'].quantile(0.80)
            target_from_pe = (avg_price_5y + high_80pct) / 2
        
        # Method 2: Analyst targets
        target_mean = info.get('targetMeanPrice', 0) or 0
        target_high = info.get('targetHighPrice', 0) or 0
        
        # Method 3: Technical resistance (1-year high at 80th percentile)
        hist_1y = stock.history(period="1y")
        resistance = hist_1y['Close'].quantile(0.80).item() if len(hist_1y) > 0 else 0.0
        
        # Combine methods (use available data)
        targets = []
        if target_from_pe and target_from_pe > current_price * 1.3:
            targets.append(target_from_pe)
        if target_mean and target_mean > current_price * 1.3:
            targets.append(target_mean)
        if resistance and resistance > current_price * 1.3:
            targets.append(resistance)
        
        if not targets:
            # Fallback: Use 80th percentile of 1-year data
            targets.append(resistance if resistance > 0 else current_price * 1.5)
        
        # Conservative estimate: average of targets
        target_avg = sum(targets) / len(targets)
        target_low = target_avg * 0.90  # -10% margin
        target_high = target_avg * 1.10  # +10% margin
        
        upside_pct = ((target_avg - current_price) / current_price) * 100
        
        return target_low, target_high, upside_pct
        
    except Exception as e:
        print(f"    ⚠️ Target estimation error: {e}")
        return None, None, None
    
def stage2_deep_analysis(candidates, memory):
    """Stage 2: Comprehensive analysis of candidates"""
    print("="*80)
    print("STAGE 2: Deep Analysis & News Check")
    print("="*80)
    
    analyzed = []
    analysis_count = 0  # Track number of stocks analyzed
    
    for candidate in candidates:
        ticker = candidate['ticker']
        
        # Check deduplication
        if not should_send_stock(ticker, memory):
            continue
        
        print(f"\nAnalyzing {ticker}...")
        
        try:
            stock, info = get_stock_with_retry(ticker)
            if not stock or not info:
                print(f"  ❌ Failed to fetch {ticker} after retries")
                continue

            if is_biotechnology_company(info):
                print(f"  ⏭️  {ticker} excluded: biotech/pharma (preference)")
                continue

            n_prof, prof_exclude = profitability_signals(info)
            if prof_exclude:
                print(f"  ⏭️  {ticker} excluded: profitability gate (3/3 negative)")
                continue
            prof_penalty = 2 if n_prof == 2 else 0
            
            excl, lev_reason = should_exclude_for_leverage(info)
            if excl:
                print(f"  ⏭️  {ticker} excluded: {lev_reason}")
                continue

            # PRICE SHAPE CHECK (sudden drop vs gradual multi-quarter decline)
            print(f"  📐 Checking price shape...")
            shape_info = analyze_price_shape(stock, candidate["current_price"])
            if shape_info["shape"] == "gradual_decline":
                print(
                    f"  ⏭️  {ticker} excluded: gradual decline shape "
                    f"(stable-period drift {shape_info['stable_drift_pct']:.0f}% "
                    f"over {shape_info['stable_years']:.1f}y — TTD-pattern, not a fallen angel)"
                )
                continue
            
            # Company name
            company_name = info.get('longName', info.get('shortName', ticker))
            
            # Market info
            market, currency = get_market_info(ticker)
            broker, alt_broker = get_broker_recommendation(market)
            
            # Financial health
            health = get_financial_health(stock)

            piotroski_score, piotroski_checks = compute_piotroski_score(info, stock)
            if (
                piotroski_score is not None
                and piotroski_score <= 2
                and piotroski_checks >= 6
            ):
                print(
                    f"  ⏭️  {ticker} excluded: Piotroski F{piotroski_score}/"
                    f"{piotroski_checks} (value-trap gate)"
                )
                continue

            forward_pe = info.get("forwardPE")
            price_to_book = info.get("priceToBook")
            short_percent = info.get("shortPercentOfFloat")
            market_cap_usd = candidate.get("market_cap") or info.get("marketCap") or 0
            
            # BANKRUPTCY RISK CHECK (AUTO-EXCLUDE)
            print(f"  🏥 Checking bankruptcy risk...")
            has_bankruptcy_risk, bankruptcy_reason = check_bankruptcy_risk(stock, info, health)
            if has_bankruptcy_risk:
                print(f"  ❌ {ticker} excluded: {bankruptcy_reason}")
                continue
            
            # Earnings calendar
            earnings_date, days_to_earnings = get_earnings_date(ticker)
            if (
                days_to_earnings is not None
                and 0 <= days_to_earnings <= EARNINGS_EXCLUDE_DAYS
            ):
                print(
                    f"  ⏭️  {ticker} excluded: earnings in {days_to_earnings} days "
                    f"({earnings_date})"
                )
                continue
            earnings_for_email = None
            days_for_email = None
            if (
                days_to_earnings is not None
                and EARNINGS_EXCLUDE_DAYS < days_to_earnings <= EARNINGS_NOTE_DAYS_MAX
            ):
                earnings_for_email = earnings_date
                days_for_email = days_to_earnings
            
            # News analysis
            print(f"  📰 Searching news...")
            news_headlines = search_recent_news(ticker, company_name)
            news_sentiment, sentiment_reason = analyze_news_sentiment(news_headlines)

            drop_21d = candidate.get("drop_21d_pct")
            is_dropping = drop_21d is not None and drop_21d < -5

            drop_from_peak_pct = None
            try:
                hist_1y = stock.history(period="1y")
                if hist_1y is not None and len(hist_1y) >= 10:
                    peak_52w = hist_1y["Close"].max().item()
                    cp = candidate["current_price"]
                    if peak_52w and peak_52w > 0:
                        drop_from_peak_pct = ((cp - peak_52w) / peak_52w) * 100
            except Exception:
                pass

            rsi_val = None
            try:
                hist_3mo = stock.history(period="3mo")
                if hist_3mo is not None and len(hist_3mo) >= 15:
                    rsi_val = compute_rsi(hist_3mo["Close"])
            except Exception:
                pass

            risk = calculate_risk_score(
                health,
                news_sentiment,
                rsi=rsi_val,
                profitability_penalty=prof_penalty,
                is_dropping=is_dropping,
                piotroski=piotroski_score,
                market_cap_usd=market_cap_usd,
                debt_ebitda=health.get("debt_ebitda") if health else None,
            )

            if risk >= 4:
                print(f"  ⏭️  {ticker} excluded: Risk score {risk}/10 (need <4)")
                continue

            print(f"  📊 Technical analysis...")
            at_bottom, wait_low, wait_high, bottom_confidence = detect_bottom(
                stock, candidate["current_price"]
            )

            target_low, target_high, upside_pct = estimate_recovery_target(
                stock, info, candidate["current_price"]
            )

            if upside_pct is None or not np.isfinite(upside_pct):
                print(f"  ⏭️  {ticker} excluded: invalid recovery estimate")
                continue
            if upside_pct < MIN_RECOVERY_POTENTIAL_PCT:
                print(
                    f"  ⏭️  {ticker} excluded: Upside {upside_pct:.0f}% "
                    f"< {MIN_RECOVERY_POTENTIAL_PCT:.0f}% target"
                )
                continue
            
            analyzed.append({
                'ticker': ticker,
                'company': company_name,
                'market': market,
                'currency': currency,
                'broker': broker,
                'alt_broker': alt_broker,
                'current_price': candidate['current_price'],
                'drop_21d_pct': drop_21d,
                'drop_from_peak_pct': drop_from_peak_pct,
                'drop_pct': drop_21d if drop_21d is not None else 0,
                'rsi': rsi_val,
                'recovery_potential': upside_pct,
                'target_low': target_low,
                'target_high': target_high,
                'risk_score': risk,
                'at_bottom': at_bottom,
                'wait_price_low': wait_low,
                'wait_price_high': wait_high,
                'bottom_confidence': bottom_confidence,
                'earnings_date': earnings_for_email,
                'days_to_earnings': days_for_email,
                'news_headlines': news_headlines[:3],  # Top 3
                'news_sentiment': news_sentiment,
                'sentiment_reason': sentiment_reason,
                'financial_health': health,
                'piotroski_score': piotroski_score,
                'piotroski_checks': piotroski_checks,
                'forward_pe': forward_pe,
                'price_to_book': price_to_book,
                'short_percent': short_percent,
                'market_cap_usd': market_cap_usd,
                'price_shape': shape_info['shape'],
                'shape_stable_years': shape_info['stable_years'],
                'shape_recent_drop_pct': shape_info['recent_drop_pct'],
            })
            
            status = "BUY NOW" if at_bottom else "WAIT"
            print(f"  ✅ {ticker} analyzed: Risk {risk}/10, {status}, Upside ~{upside_pct:.0f}%")
            
            # Increment counter and add delay every 100 analyses
            analysis_count += 1
            if analysis_count % 100 == 0:
                print(f"  ⏸️  Analyzed {analysis_count} stocks, pausing 5 seconds to avoid rate limits...")
                time.sleep(5)
            
        except Exception as e:
            print(f"  ❌ Failed to analyze {ticker}: {e}")
            continue
    
    analyzed = narrow_analyzed_results(analyzed, MAX_CANDIDATES)
    
    print(f"\n✅ Stage 2 complete: {len(analyzed)} stocks in final report (max {MAX_CANDIDATES})\n")
    return analyzed

# ============================================================================
# EMAIL GENERATION
# ============================================================================

def generate_email_html(analyzed_stocks, price_alerts):
    """Generate HTML email report"""
    
    # Sort by risk score (lowest first = best)
    analyzed_stocks.sort(key=lambda x: x['risk_score'])
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .header {{ background: #2c3e50; color: white; padding: 20px; }}
            .stock {{ border: 2px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 8px; }}
            .low-risk {{ border-left: 5px solid #27ae60; background: #eafaf1; }}
            .med-risk {{ border-left: 5px solid #f39c12; background: #fef5e7; }}
            .high-risk {{ border-left: 5px solid #e74c3c; background: #fadbd8; }}
            .news {{ background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px; }}
            .alert-box {{ background: #fff3cd; border: 2px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🌍 Multi-Market Fallen Angel Scanner</h1>
            <p>Found {len(analyzed_stocks)} recovery opportunities across 5 markets</p>
            <p>{datetime.now().strftime('%B %d, %Y at %H:%M')}</p>
        </div>
    """
    
    # Price alerts section
    if price_alerts:
        html += """
        <div class="alert-box">
            <h2>💰 AVERAGING DOWN OPPORTUNITIES</h2>
            <p>Previously sent stocks that dropped another 10%+:</p>
        """
        for alert in price_alerts:
            _, acurr = get_market_info(alert["ticker"])
            op = format_price_for_email(alert["original_price"], acurr)
            cp = format_price_for_email(alert["current_price"], acurr)
            html += f"""
            <p><strong>{alert['ticker']}</strong>: 
            {op} → {cp} 
            ({alert['additional_drop']:.1f}% additional drop since {alert['sent_date']})</p>
            """
        html += "</div>"
    
    # Summary intro
    if analyzed_stocks:
        html += """
        <p><strong>High-Quality Fallen Angels (Bankruptcy Risk: LOW, Risk Score: &lt;4/10, Upside: &ge;50%):</strong></p>
        <table style="width:100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background: #34495e; color: white;">
                <th style="padding: 10px; text-align: left;">Status</th>
                <th style="padding: 10px; text-align: left;">Ticker</th>
                <th style="padding: 10px; text-align: right;">Drop 21d</th>
                <th style="padding: 10px; text-align: right;">Drop Peak</th>
                <th style="padding: 10px; text-align: center;">RSI</th>
                <th style="padding: 10px; text-align: left;">Shape</th>
                <th style="padding: 10px; text-align: right;">Target</th>
                <th style="padding: 10px; text-align: right;">Upside</th>
                <th style="padding: 10px; text-align: center;">Risk</th>
                <th style="padding: 10px; text-align: left;">Sentiment</th>
                <th style="padding: 10px; text-align: left;">Earnings</th>
            </tr>
        """
        
        for stock in analyzed_stocks:
            risk_class = "low-risk"  # All stocks are low risk now (< 4)
            
            # Status indicator
            if stock['at_bottom']:
                status = "✅ BUY NOW"
                status_color = "#27ae60"
                price_note = ""
            else:
                status = "⏳ WAIT"
                status_color = "#f39c12"
                wait_range = f"{stock['wait_price_low']:.2f}-{stock['wait_price_high']:.2f}"
                price_note = f"<br/><small>Wait for: {wait_range} {stock['currency']}</small>"
            
            # Target price range
            target_range = f"{stock['target_low']:.2f}-{stock['target_high']:.2f}"
            
            broker_line = f"{stock['broker']}"
            if stock['alt_broker']:
                broker_line += f" {stock['alt_broker']}"

            d21 = stock.get("drop_21d_pct")
            dpeak = stock.get("drop_from_peak_pct")
            drop_21d_txt = f"{d21:.1f}%" if d21 is not None and np.isfinite(d21) else "n/a"
            drop_peak_txt = (
                f"{dpeak:.1f}%" if dpeak is not None and np.isfinite(dpeak) else "n/a"
            )
            rsi_txt = format_rsi_for_email(stock.get("rsi"))
            shape_txt = format_shape_for_email(
                stock.get("price_shape"),
                stock.get("shape_stable_years"),
                stock.get("shape_recent_drop_pct"),
            )

            if stock.get("earnings_date"):
                earnings_cell = (
                    f"📅 {stock['days_to_earnings']}d ({stock['earnings_date']})"
                )
            else:
                earnings_cell = "—"
            
            html += f"""
            <tr class="{risk_class}" style="border-bottom: 1px solid #ddd;">
                <td style="padding: 10px; color: {status_color};">
                    <strong>{status}</strong>{price_note}
                </td>
                <td style="padding: 10px;">
                    <strong>{stock['ticker']}</strong> {stock['market']}<br/>
                    <small>{broker_line}</small>
                </td>
                <td style="padding: 10px; text-align: right; color: #e74c3c;"><strong>{drop_21d_txt}</strong></td>
                <td style="padding: 10px; text-align: right; color: #e74c3c;"><strong>{drop_peak_txt}</strong></td>
                <td style="padding: 10px; text-align: center;">{rsi_txt}</td>
                <td style="padding: 10px; font-size: 12px;">{shape_txt}</td>
                <td style="padding: 10px; text-align: right; color: #27ae60;"><strong>{target_range}</strong></td>
                <td style="padding: 10px; text-align: right; color: #27ae60;"><strong>+{stock['recovery_potential']:.0f}%</strong></td>
                <td style="padding: 10px; text-align: center;"><strong>{stock['risk_score']}/10</strong></td>
                <td style="padding: 10px;">{stock['sentiment_reason']}</td>
                <td style="padding: 10px;">{earnings_cell}</td>
            </tr>
            """
        
        html += "</table>"
        
        # Detailed analysis for each stock
        html += "<h2>📊 Detailed Analysis</h2>"
        
        for stock in analyzed_stocks:
            risk_class = "low-risk"  # All are low risk now
            
            # Status
            if stock['at_bottom']:
                status_html = '<p style="color: #27ae60; font-size: 18px;"><strong>✅ BUY NOW</strong> - Technical analysis shows stock is at/near bottom</p>'
            else:
                wait_range = f"{stock['wait_price_low']:.2f}-{stock['wait_price_high']:.2f} {stock['currency']}"
                status_html = f'<p style="color: #f39c12; font-size: 18px;"><strong>⏳ WAIT</strong> - Wait for price to reach: <strong>{wait_range}</strong> (±5%)</p>'
            
            # Target estimate
            target_range = f"{stock['target_low']:.2f}-{stock['target_high']:.2f} {stock['currency']}"
            
            price_txt = format_price_for_email(
                stock["current_price"], stock.get("currency")
            )
            d21d = stock.get("drop_21d_pct")
            dpk = stock.get("drop_from_peak_pct")
            drop_detail = (
                f"21d {d21d:.1f}%"
                if d21d is not None and np.isfinite(d21d)
                else "21d n/a"
            )
            if dpk is not None and np.isfinite(dpk):
                drop_detail += f" | peak {dpk:.1f}%"

            html += f"""
            <div class="stock {risk_class}">
                <h3>{stock['ticker']}: {stock['company']}</h3>
                {status_html}
                
                <p><strong>📍 Current Price:</strong> {price_txt} (Down {drop_detail})</p>
                <p><strong>RSI:</strong> {format_rsi_for_email(stock.get('rsi'))} | 
                   <strong>🎯 Recovery Target:</strong> {target_range} (+{stock['recovery_potential']:.0f}% upside)</p>
                <p><strong>⚠️ Risk Score:</strong> {stock['risk_score']}/10 (Low) | 
                   <strong>Piotroski:</strong> {format_piotroski_for_email(stock.get('piotroski_score'), stock.get('piotroski_checks'))}</p>
                <p><strong>📐 Shape:</strong> {format_shape_for_email(stock.get('price_shape'), stock.get('shape_stable_years'), stock.get('shape_recent_drop_pct'))}</p>
                
                <p><strong>{stock['news_sentiment']}</strong>: {stock['sentiment_reason']}</p>
                
                <div class="news">
                    <strong>📰 Recent News:</strong>
                    <ul>
            """
            
            for headline in stock['news_headlines']:
                html += f"<li>{headline}</li>"
            
            html += """
                    </ul>
                </div>
            """
            
            # Financial health
            if stock['financial_health']:
                health = stock['financial_health']
                de_txt = (
                    f"{health['debt_equity_display']:.2f}"
                    if health.get('debt_equity_display') is not None
                    else "n/a (financial sector or unreliable data)"
                )
                cash_txt = format_cash_billions_for_email(
                    health.get("cash"), stock.get("currency")
                )
                rev_yoy = health.get("revenue_growth_yoy")
                rev_yoy_txt = (
                    f"{rev_yoy:.1f}%"
                    if rev_yoy is not None and np.isfinite(float(rev_yoy))
                    else "n/a"
                )
                net_debt = health.get("net_debt")
                debt_ebitda = health.get("debt_ebitda")
                net_debt_txt = (
                    f"${net_debt / 1e9:.1f}B" if net_debt is not None else "n/a"
                )
                debt_ebitda_txt = (
                    f"{debt_ebitda:.1f}x" if debt_ebitda is not None else "n/a"
                )
                stub_flag = (
                    " ⚠️ EQUITY STUB"
                    if net_debt
                    and health.get("market_cap")
                    and net_debt > health["market_cap"]
                    else ""
                )
                html += f"""
                <p><strong>💼 Financial Health (Bankruptcy Risk: LOW):</strong><br/>
                Cash: {cash_txt} | 
                Debt/Equity: {de_txt} | 
                Net debt: {net_debt_txt} | Debt/EBITDA: {debt_ebitda_txt}{stub_flag}<br/>
                Current Ratio: {health['current_ratio']:.2f} | 
                Revenue YoY: {rev_yoy_txt}</p>
                """

            fpe = stock.get("forward_pe")
            pb = stock.get("price_to_book")
            sp = stock.get("short_percent")
            fpe_txt = (
                f"{float(fpe):.1f}x"
                if fpe is not None and np.isfinite(float(fpe))
                else "n/a"
            )
            pb_txt = (
                f"{float(pb):.1f}x"
                if pb is not None and np.isfinite(float(pb))
                else "n/a"
            )
            if sp is not None and np.isfinite(float(sp)):
                short_txt = f"{float(sp) * 100:.1f}%"
                if float(sp) > 0.15:
                    short_txt += " 🔥"
            else:
                short_txt = "n/a"
            html += f"""
                <p><strong>📈 Valuation:</strong><br/>
                Forward P/E: {fpe_txt} | 
                P/B: {pb_txt} | 
                Short float: {short_txt}</p>
                """
            
            # Technical indicators
            html += f"""
            <p><strong>📊 Technical Analysis:</strong><br/>
            Bottom Detection: {stock['bottom_confidence']} confidence | 
            52-week Low Distance: Check chart for support levels</p>
            """
            
            # Earnings warning
            if stock['earnings_date']:
                html += f"""
                <p><strong>📅 Earnings:</strong> {stock['earnings_date']} ({stock['days_to_earnings']} days away) - 
                Price may be volatile around earnings</p>
                """
            
            html += "</div>"
    
    # Footer
    html += """
        <div style="margin-top: 30px; padding: 20px; background: #ecf0f1; border-radius: 5px;">
            <p><strong>📱 Broker Guide:</strong></p>
            <ul>
                <li>● Revolut = US stocks (lower fees, extended hours)</li>
                <li>● mBank eMakler = Polish, UK, German stocks</li>
                <li>● Bank Leumi = Israeli stocks (exclusive access)</li>
            </ul>
            <p>⚠️ <strong>Remember:</strong> Do your own research before investing. Check news, earnings, and assess if the drop is temporary or permanent.</p>
        </div>
        
        <p style="color: #7f8c8d; font-size: 12px;">
            Multi-Market Fallen Angel Scanner • Automated by GitHub Actions<br/>
            Markets: 🇺🇸 US • 🇵🇱 Poland • 🇬🇧 UK • 🇮🇱 Israel • 🇩🇪 Germany
        </p>
    </body>
    </html>
    """
    
    return html

def send_email(subject, html_body):
    """Send email report"""
    if not EMAIL_PASSWORD:
        print("⚠️ No EMAIL_PASSWORD found, skipping email")
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg['Subject'] = subject
        
        msg.attach(MIMEText(html_body, 'html'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Email sent: {subject}")
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "="*80)
    print("🔍 FALLEN ANGEL SCANNER v2.0")
    print("Two-Stage Process with News Analysis")
    print("="*80 + "\n")
    
    # Load memory
    memory = load_memory()
    
    # Check for price alerts first
    print("Checking for averaging down opportunities...")
    price_alerts = check_price_alerts(memory)
    if price_alerts:
        print(f"✅ Found {len(price_alerts)} averaging down alerts")
    
    # Stage 1: Quick filter
    candidates, tickers_to_remove = stage1_quick_filter()
    
    if not candidates and not price_alerts:
        print("✅ No fallen angels found today. Market looking stable!\n")
        
        # Log tickers to remove if any
        if tickers_to_remove:
            print(f"📋 Note: {len(tickers_to_remove)} tickers flagged for cleanup")
            print("   Run monthly cleanup script to remove them from ticker lists")
        return
    
    # Stage 2: Deep analysis
    analyzed_stocks = []
    if candidates:
        analyzed_stocks = stage2_deep_analysis(candidates, memory)
    
    # Generate and send email
    if analyzed_stocks or price_alerts:
        print("\n" + "="*80)
        print("GENERATING EMAIL REPORT")
        print("="*80)
        
        html = generate_email_html(analyzed_stocks, price_alerts)
        
        subject = f"🌍 Fallen Angels: {len(analyzed_stocks)} opportunities"
        if price_alerts:
            subject += f" + {len(price_alerts)} averaging down alerts"
        
        if send_email(subject, html):
            # Update memory
            for stock in analyzed_stocks:
                memory['sent_stocks'][stock['ticker']] = datetime.now().isoformat()
                memory['tracked_prices'][stock['ticker']] = {
                    'price': stock['current_price'],
                    'date': datetime.now().strftime('%Y-%m-%d')
                }
            
            save_memory(memory)
            print("✅ Memory updated")
    
    print("\n" + "="*80)
    print("✅ SCAN COMPLETE")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
