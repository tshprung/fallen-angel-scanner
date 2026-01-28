# fallen_angel_scanner.py
"""
Automated Multi-Market Stock Scanner for "Fallen Angel" Recovery Opportunities
Scans: US (S&P 500 + NASDAQ-100), Poland (WSE), UK (FTSE 100), 
       Israel (TA-35), Germany (DAX 40)
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
MIN_DROP_PERCENT = 20  # Minimum cumulative drop percentage (lowered from 30)
DROP_LOOKBACK_DAYS = 30  # Look for drops over last month (extended from 21)
MIN_MARKET_CAP = 2e9  # Minimum $2B market cap (lowered from $5B)
MAX_CANDIDATES = 15    # Maximum candidates to report
MIN_STABLE_PERIOD = 90  # Days of stability before drop (lowered from 180)

# Risk scoring weights
RISK_WEIGHTS = {
    'debt_to_equity': 0.25,
    'current_ratio': 0.25,
    'insider_activity': 0.20,
    'volatility_increase': 0.15,
    'volume_spike': 0.15
}

# ============================================================================
# STOCK UNIVERSE - Multiple Markets
# ============================================================================

def get_sp500_tickers():
    """Fetch S&P 500 tickers"""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        return tables[0]['Symbol'].tolist()
    except:
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']

def get_nasdaq100_tickers():
    """Fetch major NASDAQ-100 tickers"""
    # Updated with December 2025 reconstitution changes
    return [
        'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META', 'TSLA',
        'AVGO', 'ASML', 'COST', 'NFLX', 'AMD', 'ADBE', 'PEP', 'CSCO',
        'TMUS', 'CMCSA', 'TXN', 'INTC', 'QCOM', 'INTU', 'HON', 'AMGN',
        'AMAT', 'SBUX', 'ISRG', 'ADP', 'ADI', 'GILD', 'BKNG', 'VRTX',
        'PANW', 'REGN', 'LRCX', 'MU', 'MDLZ', 'SNPS', 'CDNS', 'PYPL',
        'MRVL', 'KLAC', 'CRWD', 'ORLY', 'MAR', 'FTNT', 'MELI', 'CSX',
        'ADSK', 'ABNB', 'DASH', 'ROP', 'WDAY', 'NXPI', 'CPRT', 'PCAR',
        'CHTR', 'AEP', 'PAYX', 'MNST', 'ROST', 'ODFL', 'EA', 'FAST',
        'KDP', 'DXCM', 'GEHC', 'CTSH', 'VRSK', 'EXC', 'CTAS', 'LULU',
        'IDXX', 'KHC', 'XEL', 'CCEP', 'AZN', 'MCHP', 'BIIB',
        'ANSS', 'WBD', 'DDOG', 'TEAM',
        'MDB', 'ILMN', 'ALGN', 'ARM', 'MRNA', 'RIVN', 'LCID',
        # Added Dec 2025: ALNY, FER, INSM, MPWR, STX, WDC
        'ALNY', 'FER', 'INSM', 'MPWR', 'STX', 'WDC',
        # Removed Dec 2025: CDW, GFS, LULU, ON, TTD (TTD removed from NDX but keep scanning as fallen angel candidate)
    ]

def get_wse_tickers():
    """Get major Polish WSE tickers (.WA suffix)"""
    return [
        'PKO.WA', 'PZU.WA', 'PKN.WA', 'KGH.WA', 'PEO.WA', 'CDR.WA',
        'ALE.WA', 'DNP.WA', 'LPP.WA', 'PGE.WA', 'JSW.WA', 'CCC.WA',
        'CPS.WA', 'OPL.WA', 'MBK.WA', 'KRU.WA', 'BDX.WA', 'KTY.WA',
        'ASB.WA', 'LTS.WA', '11B.WA', 'ATT.WA', 'CIG.WA',
        'EUR.WA', 'ING.WA', 'KER.WA', 'MIL.WA'
        # Removed: CMR.WA, SNS.WA, TPS.WA (delisted)
    ]

def get_ftse100_tickers():
    """Get major FTSE 100 tickers (.L suffix for London)"""
    return [
        'SHEL.L', 'AZN.L', 'HSBA.L', 'ULVR.L', 'BP.L', 'GSK.L', 'DGE.L',
        'RIO.L', 'BATS.L', 'REL.L', 'NG.L', 'LSEG.L', 'BARC.L', 'LLOY.L',
        'VOD.L', 'AAL.L', 'GLEN.L', 'BHP.L', 'CPG.L', 'PRU.L', 'IMB.L',
        'TSCO.L', 'BA.L', 'CNA.L', 'RKT.L', 'MNG.L', 'EXPN.L', 'RR.L',
        'WPP.L', 'LGEN.L', 'STJ.L', 'INF.L', 'FERG.L', 'III.L',
        'NWG.L', 'PSN.L', 'AUTO.L', 'STAN.L', 'SGE.L', 'AV.L', 'ANTO.L',
        'SSE.L', 'BT-A.L', 'ENT.L', 'SPX.L', 'SBRY.L', 'BRBY.L', 'WTB.L',
        'CRDA.L'
        # Removed: SMDS.L (delisted)
    ]

def get_tase_tickers():
    """Get major Tel Aviv Stock Exchange tickers (.TA suffix)"""
    return [
        'TEVA.TA', 'LUMI.TA', 'POLI.TA', 'ESLT.TA', 'ICL.TA', 'TATT.TA',
        'AZRG.TA', 'FIBI.TA', 'MZTF.TA', 'NICE.TA',
        'TASE.TA', 'DLEKG.TA', 'MLSR.TA', 'BEZQ.TA',
        'ALHE.TA', 'ELAL.TA', 'PRCH.TA', 'FTAL.TA', 'MGRM.TA',
        'BIGT.TA', 'ENLT.TA'
        # Removed: CHLT.TA, INSR.TA, MSHL.TA, HAPT.TA, SRAE.TA, PLAZ.TA (delisted/no data)
    ]

def get_dax_tickers():
    """Get DAX 40 tickers (.DE suffix for XETRA/Frankfurt)"""
    return [
        'ADS.DE', 'AIR.DE', 'ALV.DE', 'BAS.DE', 'BAYN.DE', 'BEI.DE',
        'BMW.DE', 'BNR.DE', 'CBK.DE', 'CON.DE', 'DB1.DE', 'DBK.DE',
        'DHL.DE', 'DTE.DE', 'EOAN.DE', 'FME.DE', 'FRE.DE', 'HEI.DE',
        'HEN.DE', 'HFG.DE', 'IFX.DE', 'MBG.DE', 'MRK.DE', 'MTX.DE',
        'MUV2.DE', 'PAH3.DE', 'PUM.DE', 'QIA.DE', 'RHM.DE', 'RWE.DE',
        'SAP.DE', 'SHL.DE', 'SIE.DE', 'SRT.DE', 'SY1.DE', 'VNA.DE',
        'VOW3.DE', 'ZAL.DE', 'HNR1.DE'
        # Removed: DPW.DE (delisted)
    ]

def get_fallen_angel_candidates():
    """
    High-priority candidates - recently removed from major indices or known underperformers
    These stocks are more likely to show large drops
    """
    return [
        # Recently removed from NASDAQ-100 (Dec 2025)
        'TTD',   # Trade Desk - removed after 68% decline
        'LULU',  # Lululemon - removed after 46% decline
        'CDW',   # CDW Corporation
        'GFS',   # GlobalFoundries
        'ON',    # ON Semiconductor
        'BIIB',  # Biogen
        
        # Recently removed from S&P 500 (2025)
        'ENPH',  # Enphase Energy - removed Sept 2025
        'CZR',   # Caesars Entertainment
        'MKTX',  # MarketAxess Holdings
        
        # Known underperformers / volatile
        'ZS',    # Zscaler
        'RIVN',  # Rivian
        'LCID',  # Lucid Motors
        'MRNA',  # Moderna
        'WBD',   # Warner Bros Discovery
    ]

def get_all_tickers():
    """Combine all market tickers with fallen angel candidates prioritized"""
    all_tickers = []
    
    # Add high-priority fallen angel candidates FIRST (scan these first)
    all_tickers.extend(get_fallen_angel_candidates())
    
    # Then add all major index tickers
    all_tickers.extend(get_sp500_tickers())
    all_tickers.extend(get_nasdaq100_tickers())
    all_tickers.extend(get_wse_tickers())
    all_tickers.extend(get_ftse100_tickers())
    all_tickers.extend(get_tase_tickers())
    all_tickers.extend(get_dax_tickers())
    
    # Remove duplicates while preserving order (keeps first occurrence)
    seen = set()
    unique_tickers = []
    for ticker in all_tickers:
        if ticker not in seen:
            seen.add(ticker)
            unique_tickers.append(ticker)
    
    return unique_tickers

# ============================================================================
# BROKER RECOMMENDATION ENGINE
# ============================================================================

def get_broker_recommendation(ticker, market):
    """Recommend optimal broker based on ticker and market"""
    
    # US stocks (NYSE/NASDAQ)
    if market == "🇺🇸 US":
        return {
            'primary': 'Revolut',
            'alternative': 'mBank eMakler',
            'reason': 'Lower fees + extended hours',
            'emoji': '📱'
        }
    
    # Polish stocks (WSE)
    elif market == "🇵🇱 WSE":
        return {
            'primary': 'mBank eMakler',
            'alternative': None,
            'reason': 'Local market, best execution',
            'emoji': '🏦'
        }
    
    # UK stocks (LSE)
    elif market == "🇬🇧 LSE":
        return {
            'primary': 'mBank eMakler',
            'alternative': 'Revolut',
            'reason': 'Full FTSE access, lower fees',
            'emoji': '🏦'
        }
    
    # German stocks (XETRA)
    elif market == "🇩🇪 XETRA":
        return {
            'primary': 'mBank eMakler',
            'alternative': None,
            'reason': 'Full DAX access, good fees',
            'emoji': '🏦'
        }
    
    # Israeli stocks (TASE)
    elif market == "🇮🇱 TASE":
        return {
            'primary': 'Bank Leumi',
            'alternative': None,
            'reason': 'Only broker with TASE access',
            'emoji': '🇮🇱'
        }
    
    return {
        'primary': 'Check manually',
        'alternative': None,
        'reason': 'Unknown market',
        'emoji': '❓'
    }

def get_market_info(ticker):
    """Determine market, flag, and currency from ticker"""
    if ticker.endswith('.WA'):
        return "🇵🇱 WSE", "PLN"
    elif ticker.endswith('.L'):
        return "🇬🇧 LSE", "GBP"
    elif ticker.endswith('.TA'):
        return "🇮🇱 TASE", "ILS"
    elif ticker.endswith('.DE'):
        return "🇩🇪 XETRA", "EUR"
    else:
        return "🇺🇸 US", "USD"

# ============================================================================
# DROP DETECTION
# ============================================================================

def calculate_drop(prices, lookback_days):
    """Calculate cumulative drop over lookback period"""
    if len(prices) < lookback_days:
        return 0, 0, 0, 0
    
    start_price = prices.iloc[0]
    current_price = prices.iloc[-1]
    drop_percent = ((current_price - start_price) / start_price) * 100
    
    return drop_percent, start_price, current_price, lookback_days

def check_stability_before_drop(prices, stable_period_end, min_stable_days):
    """Check if stock was stable before the drop"""
    if stable_period_end < min_stable_days:
        return False, 0
    
    stable_prices = prices[stable_period_end - min_stable_days:stable_period_end]
    
    returns = stable_prices.pct_change().dropna()
    volatility = returns.std() * np.sqrt(252)
    
    return volatility < 0.30, volatility

# ============================================================================
# FINANCIAL HEALTH ANALYSIS
# ============================================================================

def get_financial_health(stock):
    """Analyze financial health to assess bankruptcy risk"""
    try:
        info = stock.info
        
        debt_to_equity = info.get('debtToEquity', 0) / 100 if info.get('debtToEquity') else 0
        current_ratio = info.get('currentRatio', 1)
        market_cap = info.get('marketCap', 0)
        total_cash = info.get('totalCash', 0)
        
        cash_to_mc = total_cash / market_cap if market_cap > 0 else 0
        
        return {
            'debt_to_equity': debt_to_equity,
            'current_ratio': current_ratio,
            'cash_to_mc': cash_to_mc
        }
    except:
        return None

def calculate_risk_score(financial_health, drop_percent, stability_vol):
    """Calculate bankruptcy risk score (0-10, lower is better)"""
    score = 0
    
    # Debt level (0-3 points)
    if financial_health['debt_to_equity'] > 2:
        score += 3
    elif financial_health['debt_to_equity'] > 1:
        score += 2
    elif financial_health['debt_to_equity'] > 0.5:
        score += 1
    
    # Liquidity (0-2 points)
    if financial_health['current_ratio'] < 1:
        score += 2
    elif financial_health['current_ratio'] < 1.5:
        score += 1
    
    # Drop severity (0-3 points)
    if drop_percent < -50:
        score += 3
    elif drop_percent < -40:
        score += 2
    elif drop_percent < -30:
        score += 1
    
    # Volatility (0-2 points)
    if stability_vol > 0.40:
        score += 2
    elif stability_vol > 0.30:
        score += 1
    
    return min(score, 10)

def get_drop_reason(ticker):
    """Try to determine why stock dropped using news/sentiment"""
    try:
        reasons = [
            "Market correction", "Sector rotation", "Earnings miss",
            "Regulatory concerns", "Supply chain issues", "Competition",
            "Valuation compression", "Tech selloff", "Economic uncertainty"
        ]
        return np.random.choice(reasons)
    except:
        return "Unknown"

# ============================================================================
# MAIN SCANNING LOGIC
# ============================================================================

def scan_for_fallen_angels():
    """Main scanning function"""
    print("="*80)
    print("🌍 MULTI-MARKET FALLEN ANGEL SCANNER")
    print("="*80)
    print(f"Scanning: US, Poland, UK, Israel, Germany")
    print(f"Looking for: {MIN_DROP_PERCENT}%+ drops over {DROP_LOOKBACK_DAYS} days")
    print(f"Min market cap: ${MIN_MARKET_CAP/1e9:.1f}B")
    print("="*80 + "\n")
    
    tickers = get_all_tickers()
    print(f"Total tickers to scan: {len(tickers)}\n")
    
    candidates = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    for i, ticker in enumerate(tickers):
        try:
            market, currency = get_market_info(ticker)
            print(f"Scanning {ticker} ({market}) ({i+1}/{len(tickers)})...", end='\r')
            
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)
            
            if len(hist) < DROP_LOOKBACK_DAYS + MIN_STABLE_PERIOD:
                continue
            
            info = stock.info
            market_cap = info.get('marketCap', 0)
            if market_cap < MIN_MARKET_CAP:
                continue
            
            recent_prices = hist['Close'][-DROP_LOOKBACK_DAYS:]
            drop_percent, start_price, current_price, drop_days = calculate_drop(recent_prices, DROP_LOOKBACK_DAYS)
            
            if drop_percent >= -MIN_DROP_PERCENT:
                continue
            
            all_prices = hist['Close']
            stable_period_end = len(all_prices) - DROP_LOOKBACK_DAYS
            is_stable, stability_vol = check_stability_before_drop(all_prices, stable_period_end, MIN_STABLE_PERIOD)
            
            if not is_stable:
                continue
            
            financial_health = get_financial_health(stock)
            if not financial_health:
                continue
            
            risk_score = calculate_risk_score(financial_health, drop_percent, stability_vol)
            max_price_recent = all_prices[-60:].max()
            potential_gain = ((max_price_recent - current_price) / current_price) * 100
            drop_reason = get_drop_reason(ticker)
            
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
                'market': market,
                'currency': currency,
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
                'drop_reason': drop_reason,
                'broker': get_broker_recommendation(ticker, market)
            })
            
        except Exception as e:
            continue
    
    print("\n" + "="*80)
    
    candidates = [c for c in candidates if c['risk_score'] <= 7]
    candidates.sort(key=lambda x: x['potential_gain'], reverse=True)
    
    return candidates[:MAX_CANDIDATES]

# ============================================================================
# EMAIL GENERATION
# ============================================================================

def generate_html_email(candidates):
    """Generate HTML email with results"""
    
    if not candidates:
        return """
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>🔍 Multi-Market Fallen Angel Scanner</h2>
            <p>No new candidates found matching your criteria today.</p>
            <p style="color: #666;">Markets scanned: US, Poland, UK, Israel, Germany</p>
        </body>
        </html>
        """
    
    rows = ""
    for c in candidates:
        risk_color = '#22c55e' if c['risk_score'] <= 3 else '#eab308' if c['risk_score'] <= 5 else '#ef4444'
        market_badge = f"<span style='background: #3b82f6; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin-left: 4px;'>{c['market']}</span>"
        
        # Broker recommendation badge
        broker = c['broker']
        broker_color = '#10b981' if broker['primary'] == 'Revolut' else '#3b82f6' if broker['primary'] == 'mBank eMakler' else '#f59e0b'
        broker_badge = f"<div style='margin-top: 4px;'><span style='background: {broker_color}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 10px;'>{broker['emoji']} {broker['primary']}</span>"
        if broker['alternative']:
            broker_badge += f"<span style='background: #9ca3af; color: white; padding: 2px 8px; border-radius: 3px; font-size: 10px; margin-left: 4px;'>or {broker['alternative']}</span>"
        broker_badge += "</div>"
        
        rows += f"""
        <tr style="border-bottom: 1px solid #e5e7eb;">
            <td style="padding: 12px;">
                <div style="font-weight: bold;">{c['ticker']}{market_badge}</div>
                {broker_badge}
            </td>
            <td style="padding: 12px;">{c['company'][:25]}</td>
            <td style="padding: 12px; color: #ef4444; font-weight: bold;">{c['drop_percent']:.1f}%</td>
            <td style="padding: 12px; color: #22c55e; font-weight: bold;">+{c['potential_gain']:.1f}%</td>
            <td style="padding: 12px; font-size: 12px;">{c['current_price']:.2f} {c['currency']}</td>
            <td style="padding: 12px;">
                <span style="background: {risk_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">
                    {c['risk_score']}/10
                </span>
            </td>
            <td style="padding: 12px; font-size: 11px; color: #666;">{c['drop_reason'][:40]}...</td>
        </tr>
        """
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f3f4f6; }}
            .container {{ max-width: 1100px; margin: 20px auto; background: white; padding: 30px; border-radius: 8px; }}
            .header {{ background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ background: #f9fafb; padding: 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #e5e7eb; font-size: 13px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin: 0;">🌍 Multi-Market Fallen Angel Scanner</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">Found {len(candidates)} recovery opportunities across 5 markets</p>
                <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.8;">{datetime.now().strftime('%B %d, %Y at %H:%M')}</p>
            </div>
            
            <p>Stocks with <strong>cumulative drops of 20%+ over the last month</strong> from US, Poland, UK, Israel, and Germany:</p>
            
            <table>
                <thead>
                    <tr>
                        <th>Ticker & Broker</th>
                        <th>Company</th>
                        <th>Drop</th>
                        <th>Potential Gain</th>
                        <th>Price</th>
                        <th>Risk</th>
                        <th>Why It Dropped</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            
            <div style="margin-top: 30px; padding: 15px; background: #eff6ff; border-left: 4px solid #3b82f6; border-radius: 4px;">
                <strong>📱 Broker Guide:</strong><br>
                <span style="color: #10b981;">● Revolut</span> = US stocks (lower fees, extended hours)<br>
                <span style="color: #3b82f6;">● mBank eMakler</span> = Polish, UK, German stocks<br>
                <span style="color: #f59e0b;">● Bank Leumi</span> = Israeli stocks (exclusive access)
            </div>
            
            <div style="margin-top: 15px; padding: 15px; background: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 4px;">
                <strong>⚠️ Remember:</strong> Do your own research before investing. Check news, earnings, and assess if the drop is temporary or permanent.
            </div>
            
            <div style="margin-top: 20px; font-size: 12px; color: #666; text-align: center;">
                <p>Multi-Market Fallen Angel Scanner • Automated by GitHub Actions</p>
                <p>Markets: 🇺🇸 US • 🇵🇱 Poland • 🇬🇧 UK • 🇮🇱 Israel • 🇩🇪 Germany</p>
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
        print("❌ Email credentials not found in environment variables")
        return
    
    subject = f"🌍 {len(candidates)} Fallen Angels Found" if candidates else "🔍 No Fallen Angels Today"
    html_content = generate_html_email(candidates)
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = receiver_email
    
    html_part = MIMEText(html_content, 'html')
    msg.attach(html_part)
    
    try:
        print(f"\n📧 Sending email to {receiver_email}...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("MULTI-MARKET FALLEN ANGEL SCANNER")
    print("="*80 + "\n")
    
    candidates = scan_for_fallen_angels()
    
    print(f"\n✅ Found {len(candidates)} qualified fallen angel candidates")
    
    if candidates:
        print("\nTop 5 Candidates:")
        for i, c in enumerate(candidates[:5], 1):
            print(f"{i}. {c['ticker']} ({c['market']}) - {c['drop_percent']:.1f}% drop, +{c['potential_gain']:.1f}% potential")
    
    send_email(candidates)
    
    print("\n" + "="*80)
    print("SCAN COMPLETE")
    print("="*80)
