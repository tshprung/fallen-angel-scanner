# Fallen Angel Scanner

Research candidates across US, UK, German, Polish and Israeli markets. Signals are research prompts, not buy instructions or estimates of bankruptcy probability. Recovery references are not twelve-month fair values.

## Run and test

```sh
python -m pip install -r requirements.txt pytest
python -m pytest tests test_email_generation.py test_fresh_crash_bucket.py -q --import-mode=importlib -p no:cacheprovider
python scanner_entry.py
```

`scanner_entry.py` installs all production overlays. Running it with `SENDER_EMAIL`, `RECEIVER_EMAIL` and `SENDER_PASSWORD` configured sends email. The daily GitHub workflow runs tests before scanning.

## Currency normalization

Size, liquidity, cash/market-cap and net-debt/market-cap comparisons use USD. Quote metadata determines the trading currency; `financialCurrency` independently determines financial amounts. FX uses the newest valid Yahoo observation within seven calendar days, caches each pair for the run and records its observation timestamp. Missing/unsupported currencies and unavailable/stale FX skip the candidate with a diagnostic, rather than assuming USD.

GBp/GBX and ILA quote prices use a 0.01 major-unit scale. For minor-unit quotes, market cap is checked against shares outstanding and the quote price; inconsistent or missing evidence skips the candidate. Repair-mode history is reconciled back to quote units. Cash and debt are displayed in USD, while share prices and recovery references retain their quote units. Liquidity is a recent average converted at the scan's FX rate, not a historical daily-FX average. Supported major currencies: USD, GBP, EUR, PLN, ILS, CHF, CAD, AUD and JPY. Provider data and repair heuristics still need monitoring.

## Forward paper tracking

Final selections from both buckets are appended to `paper_tracking.json` independently of email delivery. Each ticker/day snapshot preserves the original selection, price, risk, recovery reference and currency evidence. Re-running the same day does not rewrite the snapshot. The scheduled workflow refreshes observations and commits the ledger and [readable report](paper_tracking_report.md).

```sh
python paper_tracking.py
```

The hypothetical entry is the first trading session after the UTC selection date, at that session's adjusted open. Only sessions before the refresh date are used, conservatively avoiding incomplete bars. An observation finishes at the first session on/after 365 calendar days from entry. The latest close provides an interim mark. Quote histories are split/dividend adjusted; returns are in the listing currency before costs, taxes and slippage. This is forward observation, not a portfolio simulation, and it does not calculate USD returns or benchmark excess returns.

The ledger distinguishes reaching 2x at a daily close from ending the twelve-month period at 2x. Missing histories remain unverified; quotes older than seven days are marked stale. Large entry/exit data gaps are unverified. This retains failed or possibly delisted names, but does not supply missing delisting proceeds. It therefore cannot yet provide an unbiased overall strategy success rate. Daily cohorts of the same stock are correlated.

Tracking starts with the next successful scheduled scan that selects candidates. The initial empty ledger contains no backfilled or simulated stock picks. Broader valuation, debt-maturity analysis, sector-specific solvency and benchmark validation remain future work. See [the original review and follow-up](SCANNER_REVIEW.md).

---

# 📦 Dependency Management Guide

Quick reference for managing Python dependencies in this project.

## 📋 Current Dependencies

See `requirements.txt` for the full list:
- **yfinance** - Fetch stock data from Yahoo Finance
- **pandas** - Data manipulation and analysis
- **numpy** - Numerical computing
- **scipy** - Required for yfinance repair-mode routines
- **lxml** - HTML/XML parsing (for Wikipedia tables)
- **requests** - HTTP library (for fetching web pages)

## 🔄 How to Update Dependencies

### Method 1: Edit requirements.txt (Recommended)

1. **Edit the file:**
   ```bash
   vim requirements.txt  # or nano, code, etc.
   ```

2. **Add, remove, or update versions:**
   ```txt
   # Add a new package
   beautifulsoup4>=4.12.0
   
   # Update version
   yfinance>=0.2.50
   
   # Remove a package
   # Just delete the line
   ```

3. **Test locally:**
   ```bash
   pip install -r requirements.txt --break-system-packages
   python fallen_angel_scanner.py  # Test scanner
   python update_tickers.py        # Test updater
   ```

4. **Commit changes:**
   ```bash
   git add requirements.txt
   git commit -m "Update dependencies: add X, update Y to v1.2"
   git push
   ```

5. **GitHub Actions will automatically use the new requirements** ✅

### Method 2: Update Workflows Directly (Not Recommended)

Only do this if you need different dependencies for different workflows.

**Edit `.github/workflows/daily-scan.yml`:**
```yaml
- name: Install dependencies
  run: |
    pip install yfinance pandas numpy new-package --break-system-packages
```

**⚠️ Downsides:**
- Have to update multiple files
- Easy to forget one
- Harder to maintain

## 🧪 Testing New Dependencies

### Local Testing
```bash
# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Test
python fallen_angel_scanner.py
python update_tickers.py
```

### GitHub Actions Testing
1. Push changes to a test branch
2. Go to Actions tab
3. Manually trigger workflow
4. Check logs for errors

## 📌 Common Updates

### Update yfinance
```txt
# In requirements.txt
yfinance>=0.2.50  # Update version number
```

### Add web scraping capability
```txt
# In requirements.txt
beautifulsoup4>=4.12.0
selenium>=4.15.0
```

### Add data visualization
```txt
# In requirements.txt
matplotlib>=3.8.0
plotly>=5.18.0
```

### Add email with attachments
```txt
# Already have standard library smtplib
# No new dependencies needed!
```

## 🔍 Checking What's Installed

### Locally
```bash
pip list
pip show yfinance  # Details about specific package
```

### In GitHub Actions
Check the workflow logs - they show exactly what gets installed.

## ⚠️ Troubleshooting

### Dependency Conflicts
```bash
# If you get conflicts
pip install --upgrade -r requirements.txt --break-system-packages

# Or start fresh
pip uninstall -y -r requirements.txt
pip install -r requirements.txt --break-system-packages
```

### Missing Dependencies in GitHub Actions
1. Check requirements.txt is committed
2. Verify workflow has `pip install -r requirements.txt`
3. Check workflow logs for errors

### Version Pinning
**Flexible (recommended for our use case):**
```txt
yfinance>=0.2.40  # Allows 0.2.40, 0.2.50, 0.3.0, etc.
```

**Strict (use if you need exact versions):**
```txt
yfinance==0.2.40  # Only allows exactly 0.2.40
```

## 📚 Best Practices

1. ✅ **Use requirements.txt** - Single source of truth
2. ✅ **Test locally first** - Before pushing
3. ✅ **Version constraints** - Use `>=` for flexibility
4. ✅ **Document changes** - In commit messages
5. ✅ **Keep it minimal** - Only add what you need

## 🎯 Quick Commands

```bash
# Install all dependencies
pip install -r requirements.txt --break-system-packages

# Update all to latest versions
pip install --upgrade -r requirements.txt --break-system-packages

# Check what's installed
pip list

# Save current environment
pip freeze > requirements-frozen.txt  # For exact reproducibility

# Check outdated packages
pip list --outdated
```

## 📝 Example: Adding a New Dependency

Let's say you want to add `python-telegram-bot` to send alerts via Telegram:

1. **Add to requirements.txt:**
   ```txt
   python-telegram-bot>=20.0.0
   ```

2. **Test locally:**
   ```bash
   pip install -r requirements.txt --break-system-packages
   ```

3. **Update your code:**
   ```python
   import telegram
   # Your telegram bot code
   ```

4. **Commit and push:**
   ```bash
   git add requirements.txt fallen_angel_scanner.py
   git commit -m "Add Telegram notifications"
   git push
   ```

5. **Done!** GitHub Actions will use the new dependency automatically.

## 🆘 Need Help?

- Check GitHub Actions logs for specific errors
- Test locally with `pip install -r requirements.txt`
- Verify requirements.txt syntax (no typos, valid package names)
- Search PyPI for exact package names: https://pypi.org
