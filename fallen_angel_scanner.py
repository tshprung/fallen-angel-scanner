# fallen_angel_scanner_v2.py
"""
Two-Stage Fallen Angel Scanner with News Analysis
Stage 1: Quick filter for price drops (fast)
Stage 2: Deep analysis only for candidates found (comprehensive)

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
import requests

# Import ticker lists
import sys
sys.path.append('/home/claude')
from tickers_config import (
    get_sp500_tickers,
    get_nasdaq100_tickers, 
    get_fallen_angel_candidates,
    get_wse_tickers,
    get_ftse100_tickers,
    get_tase_tickers,
    get_dax_tickers
)

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
MIN_MARKET_CAP = 2e9  # Minimum $2B market cap
MAX_CANDIDATES = 10  # Maximum candidates to report

# Memory/tracking
MEMORY_FILE = "scanner_memory.json"
DEDUP_DAYS = 14  # Don't re-send same stock within 14 days
PRICE_ALERT_THRESHOLD = 0.10  # Alert if stock drops another 10%

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
    
    # Get all tickers
    all_tickers = []
    all_tickers.extend(get_sp500_tickers())
    all_tickers.extend(get_nasdaq100_tickers())
    all_tickers.extend(get_wse_tickers())
    all_tickers.extend(get_ftse100_tickers())
    all_tickers.extend(get_tase_tickers())
    all_tickers.extend(get_dax_tickers())
    all_tickers.extend(get_fallen_angel_candidates())
    
    # Remove duplicates
    all_tickers = list(set(all_tickers))
    print(f"Scanning {len(all_tickers)} stocks across 5 markets\n")
    
    candidates = []
    
    for i, ticker in enumerate(all_tickers):
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(all_tickers)}")
        
        try:
            stock = yf.Ticker(ticker)
            
            # Quick checks only
            info = stock.info
            market_cap = info.get('marketCap', 0)
            
            # Filter by market cap
            if market_cap < MIN_MARKET_CAP:
                continue
            
            # Get price history
            hist = stock.history(period="1mo")
            if len(hist) < 10:
                continue
            
            current_price = hist["Close"].iloc[-1].item()
            lookback_price = hist["Close"].iloc[-min(DROP_LOOKBACK_DAYS, len(hist))].item()
            drop_pct = ((current_price - lookback_price) / lookback_price) * 100
            
            # Found a candidate!
            if drop_pct <= -MIN_DROP_PERCENT:
                candidates.append({
                    'ticker': ticker,
                    'current_price': current_price,
                    'drop_pct': drop_pct,
                    'market_cap': market_cap
                })
                print(f"  ✓ {ticker}: {drop_pct:.1f}%")
        
        except Exception as e:
            continue
    
    print(f"\n✅ Stage 1 complete: Found {len(candidates)} candidates\n")
    return candidates

# ============================================================================
# STAGE 2: DEEP ANALYSIS
# ============================================================================

def get_earnings_date(ticker):
    """Check if earnings coming soon"""
    try:
        stock = yf.Ticker(ticker)
        calendar = stock.calendar
        if calendar is not None and 'Earnings Date' in calendar.index:
            earnings_date = pd.Timestamp(calendar.loc['Earnings Date'].values[0]).tz_localize(None)
            days_until = (earnings_date - datetime.now()).days
            
            if 0 <= days_until <= 14:
                return earnings_date.strftime('%Y-%m-%d'), days_until
        return None, None
    except:
        return None, None

def search_recent_news(ticker, company_name):
    """Search for recent news about the stock"""
    try:
        # Use yfinance news first
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
        
        # Fallback: generic reasons
        return ["No specific news found - check market-wide trends"]
    
    except Exception as e:
        return [f"Unable to fetch news: {str(e)}"]

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
    """Assess bankruptcy risk from financials"""
    try:
        info = ticker_obj.info
        
        total_debt = info.get('totalDebt', 0)
        total_equity = info.get('totalStockholderEquity', 1)
        debt_to_equity = total_debt / total_equity if total_equity > 0 else 999
        
        current_assets = info.get('totalCurrentAssets', 0)
        current_liabilities = info.get('totalCurrentLiabilities', 1)
        current_ratio = current_assets / current_liabilities if current_liabilities > 0 else 0
        
        cash = info.get('totalCash', 0)
        revenue = info.get('totalRevenue', 0)
        
        return {
            'debt_to_equity': debt_to_equity,
            'current_ratio': current_ratio,
            'cash': cash,
            'revenue': revenue
        }
    except:
        return None

def calculate_risk_score(financial_health, news_sentiment):
    """Calculate risk score 1-10"""
    if not financial_health:
        return 8
    
    score = 5
    
    # Debt analysis
    if financial_health['debt_to_equity'] < 0.3:
        score -= 2
    elif financial_health['debt_to_equity'] > 1.0:
        score += 2
    
    # Liquidity
    if financial_health['current_ratio'] > 2.0:
        score -= 1
    elif financial_health['current_ratio'] < 1.0:
        score += 2
    
    # Revenue (zero revenue = speculative)
    if financial_health['revenue'] == 0:
        score += 2
    
    # News sentiment
    if "SERIOUS" in news_sentiment:
        score += 3
    elif "TEMPORARY" in news_sentiment:
        score -= 1
    
    return max(1, min(10, round(score)))

def stage2_deep_analysis(candidates, memory):
    """Stage 2: Comprehensive analysis of candidates"""
    print("="*80)
    print("STAGE 2: Deep Analysis & News Check")
    print("="*80)
    
    analyzed = []
    
    for candidate in candidates:
        ticker = candidate['ticker']
        
        # Check deduplication
        if not should_send_stock(ticker, memory):
            continue
        
        print(f"\nAnalyzing {ticker}...")
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Company name
            company_name = info.get('longName', info.get('shortName', ticker))
            
            # Market info
            market, currency = get_market_info(ticker)
            broker, alt_broker = get_broker_recommendation(market)
            
            # Financial health
            health = get_financial_health(stock)
            
            # Earnings calendar
            earnings_date, days_to_earnings = get_earnings_date(ticker)
            
            # News analysis
            print(f"  📰 Searching news...")
            news_headlines = search_recent_news(ticker, company_name)
            news_sentiment, sentiment_reason = analyze_news_sentiment(news_headlines)
            
            # Risk score
            risk = calculate_risk_score(health, news_sentiment)
            
            # Recovery potential (simple: stable high vs current)
            hist = stock.history(period="1y")
            stable_high = hist["Close"].quantile(0.80).item()
            recovery_potential = ((stable_high / candidate['current_price']) - 1) * 100
            
            analyzed.append({
                'ticker': ticker,
                'company': company_name,
                'market': market,
                'currency': currency,
                'broker': broker,
                'alt_broker': alt_broker,
                'current_price': candidate['current_price'],
                'drop_pct': candidate['drop_pct'],
                'recovery_potential': recovery_potential,
                'risk_score': risk,
                'earnings_date': earnings_date,
                'days_to_earnings': days_to_earnings,
                'news_headlines': news_headlines[:3],  # Top 3
                'news_sentiment': news_sentiment,
                'sentiment_reason': sentiment_reason,
                'financial_health': health
            })
            
            print(f"  ✅ {ticker} analyzed: Risk {risk}/10, {news_sentiment}")
            
        except Exception as e:
            print(f"  ❌ Failed to analyze {ticker}: {e}")
            continue
    
    print(f"\n✅ Stage 2 complete: {len(analyzed)} stocks fully analyzed\n")
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
            html += f"""
            <p><strong>{alert['ticker']}</strong>: 
            ${alert['original_price']:.2f} → ${alert['current_price']:.2f} 
            ({alert['additional_drop']:.1f}% additional drop since {alert['sent_date']})</p>
            """
        html += "</div>"
    
    # Summary intro
    if analyzed_stocks:
        html += """
        <p><strong>Stocks with cumulative drops of 20%+ over the last month from US, Poland, UK, Israel, and Germany:</strong></p>
        <table style="width:100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background: #34495e; color: white;">
                <th style="padding: 10px; text-align: left;">Ticker & Broker</th>
                <th style="padding: 10px; text-align: left;">Company</th>
                <th style="padding: 10px; text-align: right;">Drop</th>
                <th style="padding: 10px; text-align: right;">Potential Gain</th>
                <th style="padding: 10px; text-align: right;">Price</th>
                <th style="padding: 10px; text-align: center;">Risk</th>
                <th style="padding: 10px; text-align: left;">Why It Dropped</th>
            </tr>
        """
        
        for stock in analyzed_stocks:
            risk_class = "low-risk" if stock['risk_score'] <= 3 else "med-risk" if stock['risk_score'] <= 6 else "high-risk"
            
            # Broker line
            broker_line = f"{stock['broker']}"
            if stock['alt_broker']:
                broker_line += f" {stock['alt_broker']}"
            
            # Earnings warning
            earnings_note = ""
            if stock['earnings_date']:
                earnings_note = f"<br/>📅 Earnings in {stock['days_to_earnings']} days ({stock['earnings_date']})"
            
            html += f"""
            <tr class="{risk_class}" style="border-bottom: 1px solid #ddd;">
                <td style="padding: 10px;">
                    <strong>{stock['ticker']}</strong>{stock['market']}<br/>
                    <small>{broker_line}</small>
                </td>
                <td style="padding: 10px;">{stock['company']}</td>
                <td style="padding: 10px; text-align: right; color: #e74c3c;"><strong>{stock['drop_pct']:.1f}%</strong></td>
                <td style="padding: 10px; text-align: right; color: #27ae60;"><strong>+{stock['recovery_potential']:.1f}%</strong></td>
                <td style="padding: 10px; text-align: right;">{stock['current_price']:.2f} {stock['currency']}</td>
                <td style="padding: 10px; text-align: center;"><strong>{stock['risk_score']}/10</strong></td>
                <td style="padding: 10px;">
                    {stock['sentiment_reason']}{earnings_note}
                </td>
            </tr>
            """
        
        html += "</table>"
        
        # Detailed analysis for each stock
        html += "<h2>📊 Detailed Analysis</h2>"
        
        for stock in analyzed_stocks:
            risk_class = "low-risk" if stock['risk_score'] <= 3 else "med-risk" if stock['risk_score'] <= 6 else "high-risk"
            
            html += f"""
            <div class="stock {risk_class}">
                <h3>{stock['ticker']}: {stock['company']}</h3>
                <p><strong>Market:</strong> {stock['market']} | 
                   <strong>Price:</strong> {stock['current_price']:.2f} {stock['currency']} | 
                   <strong>Drop:</strong> {stock['drop_pct']:.1f}% | 
                   <strong>Risk:</strong> {stock['risk_score']}/10</p>
                
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
                html += f"""
                <p><strong>💼 Financial Health:</strong><br/>
                Cash: ${health['cash']/1e9:.2f}B | 
                Debt/Equity: {health['debt_to_equity']:.2f} | 
                Current Ratio: {health['current_ratio']:.2f}</p>
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
    candidates = stage1_quick_filter()
    
    if not candidates and not price_alerts:
        print("✅ No fallen angels found today. Market looking stable!\n")
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
