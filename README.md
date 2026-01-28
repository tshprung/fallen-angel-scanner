# 🌍 Multi-Market Fallen Angel Scanner

Automated stock scanner that finds "fallen angel" recovery opportunities across 5 global markets.

## 📊 What It Does

Scans ~250+ stocks across:
- 🇺🇸 US (S&P 500 + NASDAQ-100)
- 🇵🇱 Poland (WSE)
- 🇬🇧 UK (FTSE 100)
- 🇮🇱 Israel (TASE)
- 🇩🇪 Germany (DAX 40)

**Finds stocks that:**
- Dropped 20%+ in the last month
- Were stable for 3+ months before the drop
- Have low bankruptcy risk (strong financials)
- Have recovery potential

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install yfinance pandas numpy --break-system-packages
```

### 2. Set Environment Variables
```bash
export SENDER_EMAIL="your-email@gmail.com"
export SENDER_PASSWORD="your-app-password"  # Gmail App Password
export RECEIVER_EMAIL="your-email@gmail.com"
```

### 3. Run the Scanner
```bash
python fallen_angel_scanner.py
```

## 📁 File Structure

```
.
├── fallen_angel_scanner.py    # Main scanner logic
├── tickers_config.py           # Stock ticker lists (EDIT THIS)
├── fallen_angel_scanner.log   # Execution log (committed to git)
├── .gitignore                  # Git ignore rules
└── README.md                   # This file
```

## 🔧 Configuration

### Adjusting Scan Criteria

Edit `fallen_angel_scanner.py`:

```python
MIN_DROP_PERCENT = 20       # Minimum drop % (20% default)
DROP_LOOKBACK_DAYS = 30     # Time window (30 days)
MIN_MARKET_CAP = 2e9        # Min market cap ($2B)
MIN_STABLE_PERIOD = 90      # Stability period (90 days)
MAX_CANDIDATES = 15         # Max results to return
```

### Updating Stock Lists

**Edit `tickers_config.py` when:**
- Indices rebalance (NASDAQ-100: December, S&P 500: quarterly)
- You want to add/remove fallen angel candidates
- Stocks get delisted

**Key sections to update:**
1. `get_fallen_angel_candidates()` - High-priority stocks to scan first
2. `get_nasdaq100_tickers()` - Updated annually in December
3. `get_sp500_tickers()` - Auto-fetches from Wikipedia (fallback list available)

## 📧 Email Reports

Results are emailed automatically with:
- List of fallen angels found
- Drop %, potential gain, risk score
- Broker recommendation (Revolut, mBank, Bank Leumi)
- Link to company info

## 📝 Logging

All scan activity is logged to `fallen_angel_scanner.log`:
- Which stocks were scanned
- Which stocks qualified
- Any errors encountered
- Execution time

**The log file is committed to git** so you can track historical scans.

## 🔄 Automation (GitHub Actions)

Add to `.github/workflows/fallen-angel-scan.yml`:

```yaml
name: Fallen Angel Scan

on:
  schedule:
    - cron: '0 22 * * 1-5'  # Run Mon-Fri at 10 PM UTC (6 PM EST)
  workflow_dispatch:  # Manual trigger

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install yfinance pandas numpy --break-system-packages
      
      - name: Run scanner
        env:
          SENDER_EMAIL: ${{ secrets.SENDER_EMAIL }}
          SENDER_PASSWORD: ${{ secrets.SENDER_PASSWORD }}
          RECEIVER_EMAIL: ${{ secrets.RECEIVER_EMAIL }}
        run: |
          python fallen_angel_scanner.py
      
      - name: Commit log file
        run: |
          git config user.name github-actions
          git config user.email github-actions@github.com
          git add fallen_angel_scanner.log
          git diff --quiet && git diff --staged --quiet || git commit -m "Update scan log $(date +'%Y-%m-%d %H:%M')"
          git push
```

## 🛠️ Maintenance

### Quarterly Tasks
1. Check for S&P 500 changes (March, June, September, December)
2. Update `tickers_config.py` if needed

### Annual Tasks (December)
1. Check NASDAQ-100 reconstitution announcement
2. Update `get_nasdaq100_tickers()` and `get_fallen_angel_candidates()`
3. Review and clean delisted stocks from all markets

### When Stocks Get Delisted
1. Remove from appropriate function in `tickers_config.py`
2. Add comment noting removal date

## 🎯 Fallen Angel Candidates

High-priority stocks scanned FIRST (most likely to have dropped):
- Recently removed from NASDAQ-100 or S&P 500
- Known volatile stocks (RIVN, LCID, MRNA, etc.)
- Stocks from your portfolio that dropped significantly

**Update this list** in `tickers_config.py` → `get_fallen_angel_candidates()`

## 📊 Risk Scoring

Risk score (0-10, lower is better) based on:
- Debt-to-equity ratio
- Current ratio (liquidity)
- Drop severity
- Historical volatility

**Risk levels:**
- 0-3: Very Low (safest)
- 4-5: Low
- 6-7: Medium
- 8-10: High (filtered out)

## 🔍 Example Output

```
✅ Found 3 qualified fallen angel candidates

Top 5 Candidates:
1. TTD (🇺🇸 US) - -32.6% drop, +47.2% potential
2. ENPH (🇺🇸 US) - -28.1% drop, +38.5% potential
3. RIVN (🇺🇸 US) - -45.3% drop, +92.1% potential

📧 Sending email to your-email@gmail.com...
✅ Email sent successfully!
```

## ⚙️ Gmail App Password Setup

1. Go to https://myaccount.google.com/security
2. Enable 2-Factor Authentication
3. Go to "App passwords"
4. Generate password for "Mail"
5. Use this as `SENDER_PASSWORD`

## 📌 Notes

- Scan takes ~5-10 minutes for 250+ stocks
- yfinance may rate-limit aggressive scanning
- Some international tickers may have data delays
- Gmail has daily sending limits (~500 emails/day)

## 🤝 Contributing

To add new markets:
1. Create `get_MARKET_tickers()` function in `tickers_config.py`
2. Add ticker suffix to `get_market_info()`
3. Update `get_all_tickers()` to include new market

## 📜 License

MIT License - Feel free to use and modify!
