"""
Automated Ticker List Updater
Runs bi-weekly to check for index changes and flag updates needed
"""

import pandas as pd
import yfinance as yf
from datetime import datetime
import logging
import sys
import requests
from io import StringIO
from tickers_config import (
    get_sp500_tickers,
    get_nasdaq100_tickers,
    get_fallen_angel_candidates
)

# Windows consoles may default to cp1252, which cannot encode the emoji
# characters used in the log messages. Force UTF-8 when supported.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

try:
    import lxml
except ImportError:
    print("ERROR: Missing required dependency 'lxml'")
    print("Install with: pip install lxml --break-system-packages")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ticker_updates.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def _normalize_ticker(ticker):
    """Normalize index-provider symbols to Yahoo Finance style."""
    import re
    ticker = str(ticker).strip().upper()
    return re.sub(r'\.([ABC])$', r'-\1', ticker)


def fetch_sp500_from_wikipedia():
    """Fetch current S&P 500 composition from Wikipedia."""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        current_tickers = [_normalize_ticker(t) for t in tables[0]['Symbol'].dropna()]
        logger.info(f"✅ Fetched {len(current_tickers)} S&P 500 tickers from Wikipedia")
        return set(current_tickers)
    except ImportError as e:
        if 'lxml' in str(e):
            logger.error("❌ lxml not installed. Install with: pip install lxml --break-system-packages")
        else:
            logger.error(f"Import error: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch from Wikipedia: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to parse S&P 500 list: {e}")
        return None


def fetch_russell_1000_from_wikipedia():
    """Fetch current Russell 1000 constituents from Wikipedia's dedicated list page."""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_Russell_1000_companies'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))

        for table in tables:
            if 'Symbol' not in table.columns:
                continue

            symbols = table['Symbol'].dropna().astype(str).str.strip()
            tickers = [_normalize_ticker(t) for t in symbols if t and t.lower() != 'nan']

            if len(tickers) >= 500:
                logger.info(f"✅ Fetched {len(tickers)} Russell 1000 tickers from Wikipedia")
                return tickers

        logger.warning("Russell 1000 page was reachable, but no sufficiently large Symbol table was found")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch Russell 1000 from Wikipedia: {e}")
        return []
    except Exception as e:
        logger.error(f"Failed to parse Russell 1000 list: {e}")
        return []


def test_ticker_validity(ticker):
    """Test if a ticker is valid and tradeable."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if info.get('regularMarketPrice') or info.get('currentPrice'):
            return True, "Active"
        return False, "No price data"
    except Exception as e:
        return False, str(e)


def check_tickers_validity(ticker_list, market_name):
    logger.info(f"\n🔍 Checking {len(ticker_list)} {market_name} tickers...")
    invalid_tickers = []
    for i, ticker in enumerate(ticker_list, 1):
        if i % 10 == 0:
            logger.info(f"Progress: {i}/{len(ticker_list)}")
        is_valid, reason = test_ticker_validity(ticker)
        if not is_valid:
            logger.warning(f"❌ {ticker}: {reason}")
            invalid_tickers.append({'ticker': ticker, 'reason': reason})
    return invalid_tickers


def compare_sp500_lists():
    logger.info("\n" + "="*80)
    logger.info("S&P 500 COMPARISON")
    logger.info("="*80)

    current_sp500 = fetch_sp500_from_wikipedia()
    if not current_sp500:
        return None

    try:
        local_sp500 = {_normalize_ticker(t) for t in get_sp500_tickers()}
        logger.info(f"📋 Local list has {len(local_sp500)} tickers")
        if len(local_sp500) < 400:
            logger.warning("⚠️ Local list appears to be using FALLBACK")
            return {'up_to_date': True, 'additions': [], 'removals': [], 'using_fallback': True}
    except Exception as e:
        logger.error(f"Error getting local list: {e}")
        return None

    additions = current_sp500 - local_sp500
    removals = local_sp500 - current_sp500
    if not additions and not removals:
        logger.info("✅ S&P 500 list is up to date!")
        return {'up_to_date': True, 'additions': [], 'removals': [], 'using_fallback': False}

    logger.info("\n📊 Changes detected:")
    if additions:
        logger.info(f"\n➕ ADDITIONS ({len(additions)}):")
        for ticker in sorted(additions)[:10]:
            logger.info(f"   + {ticker}")
        if len(additions) > 10:
            logger.info(f"   ... and {len(additions) - 10} more")
    if removals:
        logger.info(f"\n➖ REMOVALS ({len(removals)}):")
        for ticker in sorted(removals)[:10]:
            logger.info(f"   - {ticker}")
        if len(removals) > 10:
            logger.info(f"   ... and {len(removals) - 10} more")
    return {'up_to_date': False, 'additions': list(additions), 'removals': list(removals), 'using_fallback': False}


def check_fallen_angels_still_valid():
    logger.info("\n" + "="*80)
    logger.info("FALLEN ANGEL CANDIDATES VALIDATION")
    logger.info("="*80)
    candidates = get_fallen_angel_candidates()
    invalid = check_tickers_validity(candidates, "Fallen Angel")
    logger.info("✅ All fallen angel candidates are valid!" if not invalid else f"\n❌ Found {len(invalid)} invalid fallen angel candidates:")
    return invalid


def check_nasdaq100_validity():
    logger.info("\n" + "="*80)
    logger.info("NASDAQ-100 SPOT CHECK")
    logger.info("="*80)
    invalid = check_tickers_validity(get_nasdaq100_tickers(), "NASDAQ-100")
    logger.info("✅ All NASDAQ-100 tickers are valid!" if not invalid else f"\n❌ Found {len(invalid)} invalid NASDAQ-100 tickers:")
    return invalid


def check_russell1000_fetch():
    """Verify Russell 1000 fetch returns a full universe."""
    logger.info("\n" + "="*80)
    logger.info("RUSSELL 1000 FETCH CHECK")
    logger.info("="*80)
    tickers = fetch_russell_1000_from_wikipedia()
    if len(tickers) >= 500:
        return True
    logger.warning(f"❌ Russell 1000 fetch returned only {len(tickers)} tickers (need ≥500) — scanner will use S&P 500 fallback")
    return False


def generate_update_report(sp500_changes, fallen_angels_invalid, nasdaq_invalid, russell_ok, wse_invalid, ftse_invalid, tase_invalid, dax_invalid):
    report = []
    report.append("\n" + "="*80)
    report.append("TICKER LIST UPDATE REPORT")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("="*80)
    report.append("\n## 🗂️ Russell 1000 Fetch")
    report.append("✅ Fetch OK — full universe available" if russell_ok else "❌ Fetch returned < 500 tickers — scanner using fallback S&P 500 list")
    report.append("\n## 📊 S&P 500 Status")
    if sp500_changes and sp500_changes.get('using_fallback'):
        report.append("ℹ️ Using fallback list in tickers_config.py")
    elif sp500_changes and sp500_changes['up_to_date']:
        report.append("✅ List is up to date")
    else:
        report.append("❌ Could not verify current S&P 500 list" if sp500_changes is None else "⚠️ Changes detected - manual update required!")
    for name, invalid_list in [
        ("🔥 Fallen Angel Candidates", fallen_angels_invalid),
        ("📈 NASDAQ-100", nasdaq_invalid),
        ("🇵🇱 WSE (Poland)", wse_invalid),
        ("🇬🇧 FTSE 100 (UK)", ftse_invalid),
        ("🇮🇱 TASE (Israel)", tase_invalid),
        ("🇩🇪 DAX (Germany)", dax_invalid),
    ]:
        report.append(f"\n## {name}")
        if invalid_list:
            report.append(f"❌ Found {len(invalid_list)} invalid tickers:")
            for item in invalid_list:
                report.append(f"  - {item['ticker']} ({item['reason']})")
        else:
            report.append("✅ All tickers are valid")

    action_needed = (
        not russell_ok or
        sp500_changes is None or
        (sp500_changes and not sp500_changes.get('up_to_date', False)) or
        bool(fallen_angels_invalid) or bool(nasdaq_invalid) or bool(wse_invalid) or
        bool(ftse_invalid) or bool(tase_invalid) or bool(dax_invalid)
    )
    report.append("\n## 🎯 ACTION ITEMS")
    if not russell_ok:
        report.append("\n0. Fix Russell 1000 Fetch: update any remaining callers to use the dedicated Wikipedia list page")
    if not action_needed:
        report.append("\n✅ No action needed - all lists are up to date!")
    report.append("\n" + "="*80)
    return "\n".join(report)


def main():
    logger.info("\n" + "="*80)
    logger.info("🔄 AUTOMATED TICKER LIST UPDATE CHECK")
    logger.info("="*80)

    russell_ok = check_russell1000_fetch()
    sp500_changes = compare_sp500_lists()
    fallen_angels_invalid = check_fallen_angels_still_valid()
    nasdaq_invalid = check_nasdaq100_validity()

    from tickers_config import get_wse_tickers, get_ftse100_tickers, get_tase_tickers, get_dax_tickers
    wse_invalid = check_tickers_validity(get_wse_tickers(), "WSE (Poland)")
    ftse_invalid = check_tickers_validity(get_ftse100_tickers(), "FTSE 100 (UK)")
    tase_invalid = check_tickers_validity(get_tase_tickers(), "TASE (Israel)")
    dax_invalid = check_tickers_validity(get_dax_tickers(), "DAX (Germany)")

    report = generate_update_report(
        sp500_changes, fallen_angels_invalid, nasdaq_invalid, russell_ok,
        wse_invalid, ftse_invalid, tase_invalid, dax_invalid
    )

    logger.info(report)
    report_filename = "ticker_update_report.txt"
    with open(report_filename, 'w', encoding='utf-8') as f:
        f.write(report)
    logger.info(f"\n📄 Report saved to: {report_filename}")

    action_needed = (
        not russell_ok or sp500_changes is None or
        (sp500_changes and not sp500_changes.get('up_to_date', False)) or
        bool(fallen_angels_invalid) or bool(nasdaq_invalid) or bool(wse_invalid) or
        bool(ftse_invalid) or bool(tase_invalid) or bool(dax_invalid)
    )
    return 1 if action_needed else 0


if __name__ == "__main__":
    sys.exit(main())
