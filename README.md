# 🚀 Multi-Market Fallen Angel Scanner - Setup Guide

This automated system will scan **5 major stock markets** twice daily and email you recovery opportunities.

## 📊 Markets Covered

**🇺🇸 United States:** 
- S&P 500 (~500 stocks)
- NASDAQ-100 (~100 stocks)

**🇵🇱 Poland:** WIG20 + WIG30 (~30 stocks)
- PKO BP, PZU, PKN Orlen, KGHM, CD Projekt, Allegro, Dino, LPP, etc.

**🇬🇧 United Kingdom:** FTSE 100 (~50 major stocks)
- Shell, AstraZeneca, HSBC, Unilever, BP, GSK, Diageo, Rio Tinto, etc.

**🇮🇱 Israel:** Tel Aviv Stock Exchange TA-35 (~27 stocks)
- Teva, Bank Leumi, Bank Hapoalim, Elbit Systems, ICL, Nice Systems, etc.

**🇩🇪 Germany:** DAX 40 (~40 stocks)  
- SAP, Siemens, Volkswagen, BMW, Deutsche Bank, Allianz, BASF, Bayer, etc.

**Total: ~700+ stocks scanned twice daily across 5 markets!**

## 📋 What You'll Need (5 minutes)

1. **GitHub account** (free) - [Sign up here](https://github.com/signup)
2. **Gmail account** (for sending emails) - or any email provider
3. **15 minutes** for one-time setup

---

## 🔧 Step-by-Step Setup

### Step 1: Create GitHub Repository

1. Go to [GitHub](https://github.com) and log in
2. Click the **"+"** button (top right) → **"New repository"**
3. Name it: `fallen-angel-scanner`
4. Set to **Private** (recommended) or Public
5. Check **"Add a README file"**
6. Click **"Create repository"**

---

### Step 2: Add the Scanner Files

1. In your new repository, click **"Add file"** → **"Create new file"**

2. **Create the main scanner:**
   - Name: `fallen_angel_scanner.py`
   - Copy the entire Python code from the first artifact
   - Click **"Commit changes"**

3. **Create the automation workflow:**
   - Click **"Add file"** → **"Create new file"**
   - Name: `.github/workflows/stock_scanner.yml`
   - Copy the YAML code from the second artifact
   - Click **"Commit changes"**

4. **Create requirements file:**
   - Click **"Add file"** → **"Create new file"**
   - Name: `requirements.txt`
   - Content:
     ```
     yfinance>=0.2.0
     pandas>=2.0.0
     numpy>=1.24.0
     requests>=2.31.0
     ```
   - Click **"Commit changes"**

---

### Step 3: Set Up Email (Gmail)

You need a Gmail account to send emails. Here's how to get the app password:

1. Go to your Google Account: https://myaccount.google.com/
2. Click **"Security"** (left sidebar)
3. Under "How you sign in to Google", enable **"2-Step Verification"** (if not already)
4. After enabling 2FA, go back to Security
5. Scroll down and click **"App passwords"**
6. Select:
   - App: **Mail**
   - Device: **Other** (type "Stock Scanner")
7. Click **"Generate"**
8. **Copy the 16-character password** (you'll use this in next step)

---

### Step 4: Add Email Credentials to GitHub

1. In your repository, go to **"Settings"** tab
2. Click **"Secrets and variables"** → **"Actions"**
3. Click **"New repository secret"**
4. Add three secrets:

   **Secret 1:**
   - Name: `SENDER_EMAIL`
   - Value: Your Gmail address (e.g., `yourname@gmail.com`)
   
   **Secret 2:**
   - Name: `SENDER_PASSWORD`
   - Value: The 16-character app password from Step 3
   
   **Secret 3:**
   - Name: `RECEIVER_EMAIL`
   - Value: Email where you want to receive alerts (can be same as sender)

---

### Step 5: Customize Scan Times (Optional)

The default schedule is:
- **8:00 AM CET** (7:00 UTC) - Before US market opens
- **10:00 PM CET** (21:00 UTC) - After US market closes

To change times:
1. Edit `.github/workflows/stock_scanner.yml`
2. Modify the `cron` lines:
   ```yaml
   - cron: '0 7 * * 1-5'  # Change '7' to your hour (UTC)
   - cron: '0 21 * * 1-5'  # Change '21' to your hour (UTC)
   ```
3. Use [Crontab Guru](https://crontab.guru/) to help with cron syntax

**Time conversion:** CET = UTC + 1 (or UTC + 2 in summer)

---

### Step 6: Customize Scanner Parameters (Optional)

```python
MIN_DROP_PERCENT = 30      # Cumulative drop threshold (25, 30, 35, 40%)
DROP_LOOKBACK_DAYS = 21    # Look for drops over last 14, 21, or 28 days (2-4 weeks)
MIN_MARKET_CAP = 5e9       # Minimum company size ($5B / €5B / £5B / ₪20B / 20B PLN)
MAX_CANDIDATES = 15        # How many stocks to report
```

**Important:** The scanner looks for **cumulative drops** over the period. For example:
- Stock drops 10% one week, 12% next week, 10% third week = **-32% total** ✅
- This catches both sudden crashes AND sustained sell-offs

**Market-Specific Notes:**
- **US stocks:** No suffix (e.g., AAPL, MSFT, TSLA)
- **Polish stocks:** `.WA` suffix (e.g., PKO.WA, CDR.WA)
- **UK stocks:** `.L` suffix (e.g., SHEL.L, AZN.L, HSBA.L)
- **Israeli stocks:** `.TA` suffix (e.g., TEVA.TA, LUMI.TA)
- **German stocks:** `.DE` suffix (e.g., SAP.DE, VOW3.DE, SIE.DE)
- Market cap threshold applies to all markets (~$5B equivalent)

---

### Step 7: Test It!

1. Go to **"Actions"** tab in your repository
2. Click **"Fallen Angel Stock Scanner"** workflow
3. Click **"Run workflow"** → **"Run workflow"** (green button)
4. Wait 5-10 minutes for it to complete
5. Check your email! 📧

---

## 📧 What You'll Receive

**If candidates found:**
```
Subject: 🔍 Fallen Angel Scanner - 4 candidates found

Beautiful HTML email with:
- Table of all candidates
- Drop percentages and potential gains
- Risk scores and bankruptcy assessments
- Why each stock dropped
- Direct links to research
```

**If nothing found:**
```
Subject: 🔍 Fallen Angel Scanner - No new candidates

Brief email confirming the scan ran successfully
```

---

## 🔍 Understanding the Results

### Risk Score (1-10)
- **1-3**: Very Low Risk (strong financials, low debt)
- **4-5**: Low Risk (good fundamentals)
- **6-7**: Medium Risk (some concerns)
- **8-10**: High Risk (filtered out automatically)

### Bankruptcy Risk
- **Very Low**: Excellent financial health
- **Low**: Strong balance sheet
- **Medium**: Some financial pressure
- **High**: Significant concerns

### What to Do Next
1. **Research the company** - Read recent news, earnings reports
2. **Understand WHY it dropped** - Is the problem temporary or permanent?
3. **Check the chart** - Does the pattern match your criteria?
4. **Assess your conviction** - Do you believe it will recover?
5. **Size your position** - Don't risk more than you can afford to lose

---

## 🛠️ Troubleshooting

### Scanner isn't running
- Check **Actions** tab for errors
- Verify secrets are set correctly (no typos)
- Make sure workflow file is in `.github/workflows/` folder

### Not receiving emails
- Check spam/junk folder
- Verify `RECEIVER_EMAIL` is correct
- Confirm Gmail app password is valid
- Try sending a test email manually

### Want to run more/less frequently
- Edit the `cron` schedule in workflow file
- Can run every hour, every 6 hours, once daily, etc.

### Getting errors in Actions log
- Usually means a Python package failed to install
- Check the logs in Actions tab
- The error message will guide you

---

## 💡 Pro Tips

1. **Run it manually first** to verify everything works
2. **Check Actions log** after each run to see what was found
3. **Don't act on every alert** - use your judgment
4. **Keep a trading journal** - track which signals work
5. **Adjust parameters** based on your results
6. **Add to watchlist first** - don't buy immediately

---

## 🎯 Next Steps

Once this is running, we can add:
- **Backtesting** - See what would have worked historically
- **Alert filtering** - Only email for high-conviction opportunities
- **Portfolio tracking** - Track your actual positions
- **Performance analytics** - Win rate, average gain, etc.
- **SMS alerts** - Get texts for urgent opportunities
- **Webhook integration** - Connect to Discord, Slack, etc.

---

## ⚠️ Legal Disclaimer

This is a research tool, not financial advice. Always:
- Do your own research
- Never invest more than you can afford to lose
- Understand the risks
- Consider consulting a financial advisor
- Past performance doesn't guarantee future results

---

## 📞 Need Help?

If you get stuck during setup, let me know:
- Which step you're on
- What error you're seeing
- Screenshot of the issue

I'll help you troubleshoot! 🚀

---

**Ready to start? Follow Step 1 above and let me know when you're done!**
