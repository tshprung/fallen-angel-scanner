# fallen_angel_scanner.py
"""
Automated Stock Scanner for "Fallen Angel" Recovery Opportunities
Finds stocks down 30%+ with low bankruptcy risk and recovery potential
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import requests

# ============================================================================
# CONFIGURATION
# ============================================================================

# Scanning criteria
MIN_DROP_PERCENT = 30  # Minimum drop percentage to consider
DROP_LOOKBACK_DAYS = 21  # Look for drops that happened in last 3 weeks (21 days)
MIN_DROP_WINDOW = 7     # Minimum window for the drop (can happen over 7-21 days)
MIN_MARKET_CAP = 10e9  # Minimum $10B market cap
MAX_CANDIDATES = 10    # Maximum candidates to report
MIN_STABLE_PERIOD = 180  # Days of stability before drop

# Risk scoring weights
RISK_WEIGHTS = {
    'debt_to_equity': 0.25,
    'current_ratio': 0.25,
    'insider_activity': 0.20,
    'volatility_increase': 0.15,
    'volume_spike': 0.15
}

# ============================================================================
# STOCK UNIVERSE - S&P 500 companies
# ============================================================================

def get_sp500_tickers():
    """Fetch current S&P 500 tickers from Wikipedia"""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        df = tables[0]
        return df['Symbol'].tolist()
    except:
        # Fallback to major tickers if Wikipedia fails
        return [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK-B',
            'UNH', 'JNJ', 'V', 'WMT', 'JPM', 'MA', 'PG', 'HD', 'CVX', 'MRK',
            'ABBV', 'KO', 'PEP', 'COST', 'AVGO', 'TMO', 'MCD', 'CSCO', 'ACN',
            'ABT', 'NKE', 'DHR', 'VZ', 'ADBE', 'TXN', 'NEE', 'PM', 'CRM', 'LLY'
        ]

# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

def calculate_drop(prices, lookback_days=21):
    """
    Calculate cumulative drop over the lookback period (2-3 weeks)
    This catches both sharp crashes and gradual sustained sell-offs
    """
    if len(prices) < 2:
        return 0, 0, 0, 0
    
    current_price = prices.iloc[-1]
    
    # Price from 2-3 weeks ago (starting point)
    lookback_price = prices.iloc[-min(lookback_days, len(prices))]
    
    # Cumulative drop from that starting point
    cumulative_drop = ((current_price - lookback_price) / lookback_price) * 100
    
    # Also find the highest price in this period (for potential gain calc)
    max_price = prices.max()
    
    # Days of the drop period
    drop_days = min(lookback_days, len(prices) - 1)
    
    return cumulative_drop, lookback_price, current_price, drop_days

def check_stability_before_drop(prices, drop_start_idx, lookback_days=180):
    """Check if stock was stable before the drop"""
    if drop_start_idx < lookback_days:
        return False, 0
    
    stable_period = prices[:drop_start_idx][-lookback_days:]
    volatility = (stable_period.std() / stable_period.mean()) * 100
    
    # Consider stable if volatility < 15%
    return volatility < 15, volatility

def get_financial_health(ticker_obj):
    """Assess bankruptcy risk from financials"""
    try:
        info = ticker_obj.info
        balance_sheet = ticker_obj.balance_sheet
        
        # Debt to Equity
        total_debt = info.get('totalDebt', 0)
        total_equity = info.get('totalStockholderEquity', 1)
        debt_to_equity = total_debt / total_equity if total_equity > 0 else 999
        
        # Current Ratio (liquidity)
        current_assets = info.get('totalCurrentAssets', 0)
        current_liabilities = info.get('totalCurrentLiabilities', 1)
        current_ratio = current_assets / current_liabilities if current_liabilities > 0 else 0
        
        # Cash position
        cash = info.get('totalCash', 0)
        market_cap = info.get('marketCap', 1)
        cash_to_mc = cash / market_cap if market_cap > 0 else 0
        
        return {
            'debt_to_equity': debt_to_equity,
            'current_ratio': current_ratio,
            'cash_to_mc': cash_to_mc,
            'cash': cash
        }
    except:
        return None

def calculate_risk_score(financial_health, drop_percent, stability_vol):
    """Calculate risk score 1-10 (1=safest, 10=riskiest)"""
    if not financial_health:
        return 8  # High risk if we can't get data
    
    score = 5  # Start neutral
    
    # Debt risk (lower is better)
    if financial_health['debt_to_equity'] < 0.3:
        score -= 1
    elif financial_health['debt_to_equity'] > 0.7:
        score += 1.5
    
    # Liquidity risk
    if financial_health['current_ratio'] > 2.0:
        score -= 1
    elif financial_health['current_ratio'] < 1.0:
        score += 1.5
    
    # Cash cushion
    if financial_health['cash_to_mc'] > 0.15:
        score -= 0.5
    
    # Drop severity (bigger drop = more risk, but also more opportunity)
    if abs(drop_percent) > 50:
        score += 1
    
    # Previous stability is good
    if stability_vol < 10:
        score -= 0.5
    
    return max(1, min(10, round(score)))

def get_drop_reason(ticker):
    """Try to determine why stock dropped using news/info"""
    try:
        stock = yf.Ticker(ticker)
        news = stock.news[:3] if hasattr(stock, 'news') else []
        
        if news:
            headlines = [item.get('title', '') for item in news]
            return ' | '.join(headlines)[:200]
        return "Check recent news"
    except:
        return "Unknown - research needed"

# ============================================================================
# MAIN SCANNER
# ============================================================================

def scan_for_fallen_angels():
    """Main scanning function"""
    print(f"🔍 Starting Fallen Angel scan at {datetime.now()}")
    print(f"Looking for cumulative drops ≥{MIN_DROP_PERCENT}% over last {DROP_LOOKBACK_DAYS} days\n")
    
    tickers = get_sp500_tickers()
    candidates = []
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)  # Get 1 year of data
    
    for i, ticker in enumerate(tickers):
        try:
            print(f"Scanning {ticker} ({i+1}/{len(tickers)})...", end='\r')
            
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)
            
            if len(hist) < DROP_LOOKBACK_DAYS + MIN_STABLE_PERIOD:
                continue
            
            # Get market cap
            info = stock.info
            market_cap = info.get('marketCap', 0)
            if market_cap < MIN_MARKET_CAP:
                continue
            
            # Check recent cumulative drop over 2-3 weeks
            recent_prices = hist['Close'][-DROP_LOOKBACK_DAYS:]
            drop_percent, start_price, current_price, drop_days = calculate_drop(recent_prices, DROP_LOOKBACK_DAYS)
            
            if drop_percent >= -MIN_DROP_PERCENT:  # We want negative drops
                continue
            
            # Check if it was stable before the drop period
            all_prices = hist['Close']
            stable_period_end = len(all_prices) - DROP_LOOKBACK_DAYS
            is_stable, stability_vol = check_stability_before_drop(
                all_prices, stable_period_end, MIN_STABLE_PERIOD
            )
            
            if not is_stable:
                continue
            
            # Get financial health
            financial_health = get_financial_health(stock)
            if not financial_health:
                continue
            
            # Calculate metrics
            risk_score = calculate_risk_score(financial_health, drop_percent, stability_vol)
            
            # Find the peak price in recent history for potential gain calculation
            max_price_recent = all_prices[-60:].max()  # Last 2-3 months peak
            potential_gain = ((max_price_recent - current_price) / current_price) * 100
            
            # Get drop reason
            drop_reason = get_drop_reason(ticker)
            
            # Bankruptcy risk assessment
            if risk_score <= 3:
                bankruptcy_risk = "Very Low"
            elif risk_score <= 5:
                bankruptcy_risk = "Low"
            elif risk_score <= 7:
                bankruptcy_risk = "Medium"
            else:
                bankruptcy_risk = "High"
            
            candidates.append({
                'ticker': ticker,
                'company': info.get('longName', ticker),
                'current_price': current_price,
                'drop_percent': drop_percent,
                'drop_days': drop_days,
                'previous_high': max_price_recent,
                'potential_gain': potential_gain,
                'market_cap': market_cap,
                'risk_score': risk_score,
                'bankruptcy_risk': bankruptcy_risk,
                'debt_to_equity': financial_health['debt_to_equity'],
                'current_ratio': financial_health['current_ratio'],
                'cash_position': 'Strong' if financial_health['cash_to_mc'] > 0.15 else 'Moderate',
                'stability_vol': stability_vol,
                'drop_reason': drop_reason
            })
            
        except Exception as e:
            continue
    
    print("\n" + "="*80)
    
    # Sort by potential gain and filter by risk
    candidates = [c for c in candidates if c['risk_score'] <= 7]  # Filter out highest risk
    candidates.sort(key=lambda x: x['potential_gain'], reverse=True)
    
    return candidates[:MAX_CANDIDATES]

# ============================================================================
# EMAIL GENERATION
# ============================================================================

def generate_html_email(candidates):
    """Generate beautiful HTML email with results"""
    
    if not candidates:
        return """
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>🔍 Fallen Angel Scanner</h2>
            <p>No new candidates found matching your criteria today.</p>
            <p style="color: #666;">The scanner ran successfully but didn't find any stocks with 30%+ drops that meet the quality filters.</p>
        </body>
        </html>
        """
    
    rows = ""
    for c in candidates:
        risk_color = '#22c55e' if c['risk_score'] <= 3 else '#eab308' if c['risk_score'] <= 5 else '#ef4444'
        rows += f"""
        <tr style="border-bottom: 1px solid #e5e7eb;">
            <td style="padding: 12px; font-weight: bold;">{c['ticker']}</td>
            <td style="padding: 12px;">{c['company'][:30]}</td>
            <td style="padding: 12px; color: #ef4444; font-weight: bold;">{c['drop_percent']:.1f}%</td>
            <td style="padding: 12px; color: #22c55e; font-weight: bold;">+{c['potential_gain']:.1f}%</td>
            <td style="padding: 12px;">
                <span style="background: {risk_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">
                    {c['risk_score']}/10
                </span>
            </td>
            <td style="padding: 12px; font-size: 12px;">{c['bankruptcy_risk']}</td>
            <td style="padding: 12px; font-size: 11px; color: #666;">{c['drop_reason'][:60]}...</td>
        </tr>
        """
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f3f4f6; }}
            .container {{ max-width: 1000px; margin: 20px auto; background: white; padding: 30px; border-radius: 8px; }}
            .header {{ background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ background: #f9fafb; padding: 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #e5e7eb; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin: 0;">🔍 Fallen Angel Scanner Results</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">Found {len(candidates)} recovery opportunities</p>
                <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.8;">{datetime.now().strftime('%B %d, %Y at %H:%M')}</p>
            </div>
            
            <p>Stocks with <strong>cumulative drops of 30%+ over the last 2-3 weeks</strong> that show potential for recovery:</p>
            
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Company</th>
                        <th>Cumulative Drop</th>
                        <th>Potential Gain</th>
                        <th>Risk</th>
                        <th>Bankruptcy Risk</th>
                        <th>Why It Dropped</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            
            <div style="margin-top: 30px; padding: 15px; background: #eff6ff; border-left: 4px solid #3b82f6; border-radius: 4px;">
                <strong>⚠️ Remember:</strong> Do your own research before investing. Check news, earnings, and assess if the drop is temporary or permanent.
            </div>
            
            <div style="margin-top: 20px; font-size: 12px; color: #666; text-align: center;">
                <p>Fallen Angel Scanner • Automated by GitHub Actions</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

def send_email(candidates):
    """Send email with results"""
    sender_email = os.environ.get('SENDER_EMAIL')
    sender_password = os.environ.get('SENDER_PASSWORD')
    receiver_email = os.environ.get('RECEIVER_EMAIL')
    
    if not all([sender_email, sender_password, receiver_email]):
        print("❌ Email credentials not configured")
        return
    
    subject = f"🔍 Fallen Angel Scanner - {len(candidates)} candidates found" if candidates else "🔍 Fallen Angel Scanner - No new candidates"
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = receiver_email
    
    html_body = generate_html_email(candidates)
    msg.attach(MIMEText(html_body, 'html'))
    
    try:
        # Using Gmail SMTP
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print(f"✅ Email sent successfully to {receiver_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    candidates = scan_for_fallen_angels()
    
    print(f"\n✅ Scan complete! Found {len(candidates)} candidates\n")
    
    if candidates:
        print("Top candidates:")
        for c in candidates[:5]:
            print(f"  {c['ticker']:6} - Drop: {c['drop_percent']:6.1f}% | Gain Potential: +{c['potential_gain']:5.1f}% | Risk: {c['risk_score']}/10")
    
    # Send email
    send_email(candidates)
    
    print("\n" + "="*80)
    print("Done! 🎉")
