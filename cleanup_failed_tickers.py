#!/usr/bin/env python3
"""
Monthly Ticker Cleanup Script
Removes tickers that have failed 3+ times from ticker lists
Run this once per month via GitHub Actions or manually
"""

import json
import os
from datetime import datetime

FAILED_TICKER_FILE = "failed_tickers.json"

def load_failed_tickers():
    """Load failed ticker tracking"""
    try:
        if os.path.exists(FAILED_TICKER_FILE):
            with open(FAILED_TICKER_FILE, 'r') as f:
                return json.load(f)
        return {}
    except:
        return {}

def get_tickers_to_remove(failed_tickers, min_failures=3):
    """Get list of tickers that should be removed"""
    to_remove = []
    for ticker, data in failed_tickers.items():
        if data["count"] >= min_failures:
            to_remove.append({
                'ticker': ticker,
                'failures': data['count'],
                'last_failure': data['last_failure'],
                'reason': data['reason']
            })
    return to_remove

def main():
    print("="*80)
    print("🧹 TICKER CLEANUP SCRIPT")
    print("="*80 + "\n")
    
    failed_tickers = load_failed_tickers()
    
    if not failed_tickers:
        print("✅ No failed tickers tracked. Nothing to clean up!\n")
        return
    
    print(f"Found {len(failed_tickers)} tickers with failures\n")
    
    tickers_to_remove = get_tickers_to_remove(failed_tickers)
    
    if not tickers_to_remove:
        print("✅ No tickers meet removal criteria (3+ failures)\n")
        return
    
    print(f"⚠️  {len(tickers_to_remove)} tickers flagged for removal:\n")
    
    # Group by reason
    by_reason = {}
    for item in tickers_to_remove:
        reason = item['reason']
        if reason not in by_reason:
            by_reason[reason] = []
        by_reason[reason].append(item['ticker'])
    
    for reason, tickers in by_reason.items():
        print(f"\n{reason}:")
        for ticker in sorted(tickers):
            print(f"  - {ticker}")
    
    print("\n" + "="*80)
    print("MANUAL CLEANUP REQUIRED")
    print("="*80)
    print("\nTo remove these tickers:")
    print("1. Edit tickers_config.py")
    print("2. Remove tickers from their respective lists")
    print("3. Commit changes to GitHub")
    print("4. Delete failed_tickers.json to reset tracking")
    print("\nTickers to remove:")
    print(", ".join([t['ticker'] for t in tickers_to_remove]))
    print()
    
    # Save report
    report_file = f"ticker_cleanup_report_{datetime.now().strftime('%Y%m%d')}.txt"
    with open(report_file, 'w') as f:
        f.write("TICKER CLEANUP REPORT\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total tickers to remove: {len(tickers_to_remove)}\n\n")
        
        for reason, tickers in by_reason.items():
            f.write(f"\n{reason}:\n")
            for ticker in sorted(tickers):
                f.write(f"  {ticker}\n")
        
        f.write("\n\nFull list (comma-separated):\n")
        f.write(", ".join([t['ticker'] for t in tickers_to_remove]))
    
    print(f"📄 Report saved: {report_file}\n")

if __name__ == "__main__":
    main()
