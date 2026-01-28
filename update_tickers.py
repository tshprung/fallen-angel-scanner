"""
Automated Ticker List Updater
Runs bi-weekly to check for index changes and flag updates needed

This script:
1. Fetches current S&P 500 composition from Wikipedia
2. Compares with local lists to detect changes
3. Flags additions/removals
4. Generates update report
5. (Optionally) Auto-commits changes to git

Run: python update_tickers.py
"""

import pandas as pd
import yfinance as yf
from datetime import datetime
import logging
from tickers_config import (
    get_sp500_tickers, 
    get_nasdaq100_tickers,
    get_fallen_angel_candidates
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ticker_updates.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# FETCH CURRENT INDEX COMPOSITIONS
# ============================================================================

def fetch_sp500_from_wikipedia():
    """Fetch current S&P 500 composition from Wikipedia"""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        current_tickers = tables[0]['Symbol'].tolist()
        logger.info(f"✅ Fetched {len(current_tickers)} S&P 500 tickers from Wikipedia")
        return set(current_tickers)
    except Exception as e:
        logger.error(f"Failed to fetch S&P 500 list: {e}")
        return None

def test_ticker_validity(ticker):
    """Test if a ticker is valid and tradeable"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Check if we can get basic info
        if info.get('regularMarketPrice') or info.get('currentPrice'):
            return True, "Active"
        else:
            return False, "No price data"
    except Exception as e:
        return False, str(e)

def check_tickers_validity(ticker_list, market_name):
    """Check validity of a list of tickers"""
    logger.info(f"\n🔍 Checking {len(ticker_list)} {market_name} tickers...")
    
    invalid_tickers = []
    
    for i, ticker in enumerate(ticker_list, 1):
        if i % 10 == 0:
            logger.info(f"Progress: {i}/{len(ticker_list)}")
        
        is_valid, reason = test_ticker_validity(ticker)
        
        if not is_valid:
            logger.warning(f"❌ {ticker}: {reason}")
            invalid_tickers.append({
                'ticker': ticker,
                'reason': reason
            })
    
    return invalid_tickers

# ============================================================================
# COMPARE LISTS AND DETECT CHANGES
# ============================================================================

def compare_sp500_lists():
    """Compare our S&P 500 list with current Wikipedia list"""
    logger.info("\n" + "="*80)
    logger.info("S&P 500 COMPARISON")
    logger.info("="*80)
    
    # Fetch current from Wikipedia
    current_sp500 = fetch_sp500_from_wikipedia()
    if not current_sp500:
        return None
    
    # Get our local list
    try:
        local_sp500 = set(get_sp500_tickers())
        logger.info(f"📋 Local list has {len(local_sp500)} tickers")
    except:
        # Fallback list is being used
        logger.warning("⚠️  Using fallback S&P 500 list (Wikipedia fetch failed previously)")
        return None
    
    # Find differences
    additions = current_sp500 - local_sp500
    removals = local_sp500 - current_sp500
    
    if not additions and not removals:
        logger.info("✅ S&P 500 list is up to date!")
        return {
            'up_to_date': True,
            'additions': [],
            'removals': []
        }
    
    logger.info(f"\n📊 Changes detected:")
    
    if additions:
        logger.info(f"\n➕ ADDITIONS ({len(additions)}):")
        for ticker in sorted(additions):
            logger.info(f"   + {ticker}")
    
    if removals:
        logger.info(f"\n➖ REMOVALS ({len(removals)}):")
        for ticker in sorted(removals):
            logger.info(f"   - {ticker}")
    
    return {
        'up_to_date': False,
        'additions': list(additions),
        'removals': list(removals)
    }

def check_fallen_angels_still_valid():
    """Check if fallen angel candidates are still valid tickers"""
    logger.info("\n" + "="*80)
    logger.info("FALLEN ANGEL CANDIDATES VALIDATION")
    logger.info("="*80)
    
    candidates = get_fallen_angel_candidates()
    invalid = check_tickers_validity(candidates, "Fallen Angel")
    
    if invalid:
        logger.info(f"\n❌ Found {len(invalid)} invalid fallen angel candidates:")
        for item in invalid:
            logger.info(f"   {item['ticker']}: {item['reason']}")
        return invalid
    else:
        logger.info("✅ All fallen angel candidates are valid!")
        return []

def check_nasdaq100_validity():
    """Spot check NASDAQ-100 tickers for validity"""
    logger.info("\n" + "="*80)
    logger.info("NASDAQ-100 SPOT CHECK")
    logger.info("="*80)
    
    nasdaq_tickers = get_nasdaq100_tickers()
    invalid = check_tickers_validity(nasdaq_tickers, "NASDAQ-100")
    
    if invalid:
        logger.info(f"\n❌ Found {len(invalid)} invalid NASDAQ-100 tickers:")
        for item in invalid:
            logger.info(f"   {item['ticker']}: {item['reason']}")
        return invalid
    else:
        logger.info("✅ All NASDAQ-100 tickers are valid!")
        return []

# ============================================================================
# GENERATE UPDATE REPORT
# ============================================================================

def generate_update_report(sp500_changes, fallen_angels_invalid, nasdaq_invalid):
    """Generate comprehensive update report"""
    
    report = []
    report.append("\n" + "="*80)
    report.append("TICKER LIST UPDATE REPORT")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("="*80)
    
    # S&P 500 Changes
    report.append("\n## 📊 S&P 500 Status")
    if sp500_changes:
        if sp500_changes['up_to_date']:
            report.append("✅ List is up to date")
        else:
            report.append("⚠️  Changes detected - manual update required!")
            report.append("\n### Additions:")
            for ticker in sp500_changes['additions']:
                report.append(f"  + {ticker}")
            report.append("\n### Removals:")
            for ticker in sp500_changes['removals']:
                report.append(f"  - {ticker}")
    else:
        report.append("❌ Could not fetch current S&P 500 list")
    
    # Fallen Angel Candidates
    report.append("\n## 🔥 Fallen Angel Candidates")
    if fallen_angels_invalid:
        report.append(f"❌ Found {len(fallen_angels_invalid)} invalid tickers - REMOVE THESE:")
        for item in fallen_angels_invalid:
            report.append(f"  - {item['ticker']} ({item['reason']})")
    else:
        report.append("✅ All candidates are valid")
    
    # NASDAQ-100
    report.append("\n## 📈 NASDAQ-100")
    if nasdaq_invalid:
        report.append(f"❌ Found {len(nasdaq_invalid)} invalid tickers - REMOVE THESE:")
        for item in nasdaq_invalid:
            report.append(f"  - {item['ticker']} ({item['reason']})")
    else:
        report.append("✅ All tickers are valid")
    
    # Action Items
    report.append("\n## 🎯 ACTION ITEMS")
    action_needed = False
    
    if sp500_changes and not sp500_changes['up_to_date']:
        report.append("\n1. Update S&P 500 list:")
        report.append("   - Wikipedia auto-fetches, but you may want to verify additions/removals")
        action_needed = True
    
    if fallen_angels_invalid:
        report.append("\n2. Update Fallen Angel Candidates in tickers_config.py:")
        report.append("   - Remove invalid tickers listed above")
        report.append("   - Consider adding recently delisted index stocks")
        action_needed = True
    
    if nasdaq_invalid:
        report.append("\n3. Update NASDAQ-100 list in tickers_config.py:")
        report.append("   - Remove invalid tickers listed above")
        report.append("   - Check https://www.nasdaq.com/solutions/nasdaq-100 for replacements")
        action_needed = True
    
    if not action_needed:
        report.append("\n✅ No action needed - all lists are up to date!")
    
    report.append("\n" + "="*80)
    
    return "\n".join(report)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Run full ticker list update check"""
    
    logger.info("\n" + "="*80)
    logger.info("🔄 AUTOMATED TICKER LIST UPDATE CHECK")
    logger.info("="*80)
    
    # 1. Check S&P 500
    sp500_changes = compare_sp500_lists()
    
    # 2. Validate Fallen Angel Candidates
    fallen_angels_invalid = check_fallen_angels_still_valid()
    
    # 3. Spot check NASDAQ-100
    nasdaq_invalid = check_nasdaq100_validity()
    
    # 4. Generate report
    report = generate_update_report(sp500_changes, fallen_angels_invalid, nasdaq_invalid)
    
    # 5. Log and save report
    logger.info(report)
    
    # Save report to file
    report_filename = f"ticker_update_report_{datetime.now().strftime('%Y%m%d')}.txt"
    with open(report_filename, 'w') as f:
        f.write(report)
    
    logger.info(f"\n📄 Report saved to: {report_filename}")
    
    # 6. Determine if action needed
    action_needed = (
        (sp500_changes and not sp500_changes['up_to_date']) or
        fallen_angels_invalid or
        nasdaq_invalid
    )
    
    if action_needed:
        logger.warning("\n⚠️  ACTION REQUIRED: Please review the report and update tickers_config.py")
        return 1  # Exit code 1 = action needed
    else:
        logger.info("\n✅ ALL CLEAR: No updates needed!")
        return 0  # Exit code 0 = all good

if __name__ == "__main__":
    exit(main())
