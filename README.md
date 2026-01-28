# 📦 Dependency Management Guide

Quick reference for managing Python dependencies in this project.

## 📋 Current Dependencies

See `requirements.txt` for the full list:
- **yfinance** - Fetch stock data from Yahoo Finance
- **pandas** - Data manipulation and analysis
- **numpy** - Numerical computing
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
