"""
Ticker Configuration File
Last updated: January 2026

This file contains all stock ticker lists for the fallen angel scanner.
Update this file when indices rebalance (quarterly for S&P 500, annually for NASDAQ-100 in December).
"""

# ============================================================================
# HIGH-PRIORITY FALLEN ANGEL CANDIDATES
# ============================================================================

def get_fallen_angel_candidates():
    """
    High-priority candidates - recently removed from major indices or known underperformers
    These stocks are scanned FIRST as they're most likely to show large drops
    
    Update this list when:
    - Stocks are removed from NASDAQ-100 (December rebalance)
    - Stocks are removed from S&P 500 (quarterly rebalances)
    - You notice other volatile stocks worth monitoring
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
        
        # Known underperformers / volatile stocks
        'ZS',    # Zscaler
        'RIVN',  # Rivian
        'LCID',  # Lucid Motors
        'MRNA',  # Moderna
        'WBD',   # Warner Bros Discovery
        'INTC',  # Intel - significant decline
    ]

# ============================================================================
# US STOCKS - S&P 500
# ============================================================================

def get_sp500_tickers():
    """
    Fetch S&P 500 tickers from Wikipedia
    Fallback to major tech stocks if fetch fails
    
    S&P 500 rebalances quarterly (March, June, September, December)
    Check for updates at: https://www.spglobal.com/spdji/en/indices/equity/sp-500/
    """
    try:
        import pandas as pd
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        return tables[0]['Symbol'].tolist()
    except:
        # Fallback: Top 50 US stocks by market cap
        return [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA',
            'BRK.B', 'LLY', 'V', 'UNH', 'XOM', 'WMT', 'JPM', 'MA',
            'JNJ', 'PG', 'AVGO', 'HD', 'CVX', 'MRK', 'ABBV', 'COST',
            'KO', 'PEP', 'BAC', 'NFLX', 'TMO', 'CRM', 'AMD', 'MCD',
            'CSCO', 'ACN', 'LIN', 'ADBE', 'ORCL', 'ABT', 'WFC', 'DHR',
            'NKE', 'CMCSA', 'TXN', 'DIS', 'PM', 'VZ', 'BMY', 'INTC',
            'UPS', 'NEE', 'RTX'
        ]

# ============================================================================
# US STOCKS - NASDAQ-100
# ============================================================================

def get_nasdaq100_tickers():
    """
    NASDAQ-100 tickers (manually maintained)
    
    NASDAQ-100 rebalances annually in December
    Last update: December 2025
    Next update: December 2026
    
    Check for updates at: https://www.nasdaq.com/solutions/nasdaq-100
    """
    return [
        # Mega-cap tech
        'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META', 'TSLA',
        
        # Large-cap tech & growth
        'AVGO', 'ASML', 'COST', 'NFLX', 'AMD', 'ADBE', 'PEP', 'CSCO',
        'TMUS', 'CMCSA', 'TXN', 'INTC', 'QCOM', 'INTU', 'HON', 'AMGN',
        'AMAT', 'SBUX', 'ISRG', 'ADP', 'ADI', 'GILD', 'BKNG', 'VRTX',
        
        # Mid-cap tech & growth
        'PANW', 'REGN', 'LRCX', 'MU', 'MDLZ', 'SNPS', 'CDNS', 'PYPL',
        'MRVL', 'KLAC', 'CRWD', 'ORLY', 'MAR', 'FTNT', 'MELI', 'CSX',
        'ADSK', 'ABNB', 'DASH', 'ROP', 'WDAY', 'NXPI', 'CPRT', 'PCAR',
        
        # Small-cap & speculative
        'CHTR', 'AEP', 'PAYX', 'MNST', 'ROST', 'ODFL', 'EA', 'FAST',
        'KDP', 'DXCM', 'GEHC', 'CTSH', 'VRSK', 'EXC', 'CTAS',
        'IDXX', 'KHC', 'XEL', 'CCEP', 'AZN', 'MCHP', 'BIIB',
        'ANSS', 'WBD', 'DDOG', 'TEAM',
        'MDB', 'ILMN', 'ALGN', 'ARM', 'MRNA', 'RIVN', 'LCID',
        
        # Added December 2025
        'ALNY',  # Alnylam Pharmaceuticals
        'FER',   # Ferrovial
        'INSM',  # Insmed
        'MPWR',  # Monolithic Power Systems
        'STX',   # Seagate Technology (up 200%+ in 2025)
        'WDC',   # Western Digital (up 238% in 2025)
        
        # Removed December 2025 (now in fallen_angel_candidates):
        # TTD, LULU, CDW, GFS, ON
    ]

# ============================================================================
# POLAND - WARSAW STOCK EXCHANGE (WSE)
# ============================================================================

def get_wse_tickers():
    """
    Major Polish WSE tickers (.WA suffix)
    WIG30 and WIG20 components
    
    Last cleaned: January 2026 (removed 3 delisted stocks)
    Check for updates at: https://www.gpw.pl/indices
    """
    return [
        # Large-cap
        'PKO.WA',   # PKO Bank Polski
        'PZU.WA',   # PZU Insurance
        'PKN.WA',   # PKN Orlen (oil)
        'KGH.WA',   # KGHM (copper)
        'PEO.WA',   # Pekao Bank
        'CDR.WA',   # CD Projekt
        'ALE.WA',   # Allegro
        'DNP.WA',   # Dino Polska
        'LPP.WA',   # LPP (fashion)
        'PGE.WA',   # PGE Energy
        
        # Mid-cap
        'JSW.WA',   # JSW (coal)
        'CCC.WA',   # CCC (shoes)
        'CPS.WA',   # Cyfrowy Polsat
        'OPL.WA',   # Orange Polska
        'MBK.WA',   # mBank
        'KRU.WA',   # Kruk
        'BDX.WA',   # Budimex
        'KTY.WA',   # Kęty
        'ASB.WA',   # Asseco Business Solutions
        'LTS.WA',   # Lubelski Węgiel Bogdanka
        
        # Small-cap
        '11B.WA',   # 11 bit studios
        'ATT.WA',   # Atende
        'CIG.WA',   # Cigames
        'EUR.WA',   # Eurocash
        'ING.WA',   # ING Bank Śląski
        'KER.WA',   # Kernel
        'MIL.WA',   # Millenium Bank
    ]

# ============================================================================
# UK - LONDON STOCK EXCHANGE (LSE)
# ============================================================================

def get_ftse100_tickers():
    """
    Major FTSE 100 tickers (.L suffix for London)
    
    Last cleaned: January 2026 (removed 1 delisted stock)
    Check for updates at: https://www.londonstockexchange.com/indices/ftse-100
    """
    return [
        # Energy & Resources
        'SHEL.L',   # Shell
        'BP.L',     # BP
        'RIO.L',    # Rio Tinto
        'GLEN.L',   # Glencore
        'BHP.L',    # BHP Group
        'ANTO.L',   # Antofagasta
        
        # Financials
        'HSBA.L',   # HSBC
        'BARC.L',   # Barclays
        'LLOY.L',   # Lloyds
        'NWG.L',    # NatWest
        'STAN.L',   # Standard Chartered
        'LSEG.L',   # London Stock Exchange
        'PRU.L',    # Prudential
        'LGEN.L',   # Legal & General
        'III.L',    # 3i Group
        
        # Consumer
        'AZN.L',    # AstraZeneca
        'ULVR.L',   # Unilever
        'DGE.L',    # Diageo
        'BATS.L',   # British American Tobacco
        'REL.L',    # RELX
        'TSCO.L',   # Tesco
        'SBRY.L',   # Sainsbury's
        'BRBY.L',   # Burberry
        
        # Industrial & Tech
        'NG.L',     # National Grid
        'SSE.L',    # SSE
        'BA.L',     # BAE Systems
        'RR.L',     # Rolls-Royce
        'RKT.L',    # Reckitt
        'WPP.L',    # WPP
        'EXPN.L',   # Experian
        'CNA.L',    # Centrica
        'VOD.L',    # Vodafone
        'BT-A.L',   # BT Group
        'AAL.L',    # Anglo American
        
        # Other major components
        'GSK.L', 'CPG.L', 'IMB.L', 'MNG.L', 'STJ.L',
        'INF.L', 'FERG.L', 'PSN.L', 'AUTO.L', 'SGE.L',
        'AV.L', 'ENT.L', 'SPX.L', 'WTB.L', 'CRDA.L'
    ]

# ============================================================================
# ISRAEL - TEL AVIV STOCK EXCHANGE (TASE)
# ============================================================================

def get_tase_tickers():
    """
    Major Tel Aviv Stock Exchange tickers (.TA suffix)
    TA-35 and TA-125 components
    
    Last cleaned: January 2026 (removed 6 delisted stocks)
    Check for updates at: https://www.tase.co.il/en/indices/
    """
    return [
        # Large-cap
        'TEVA.TA',   # Teva Pharmaceutical
        'LUMI.TA',   # Bank Leumi
        'POLI.TA',   # Bank Hapoalim
        'ESLT.TA',   # Elbit Systems
        'ICL.TA',    # ICL Group
        'TATT.TA',   # Teva Tech
        'AZRG.TA',   # Azrieli Group
        'NICE.TA',   # NICE Systems
        
        # Mid-cap
        'FIBI.TA',   # First International Bank
        'MZTF.TA',   # Mizrahi Tefahot Bank
        'TASE.TA',   # Tel Aviv Stock Exchange
        'DLEKG.TA',  # Delek Group
        'MLSR.TA',   # Melisron
        'BEZQ.TA',   # Bezeq Telecom
        
        # Small-cap
        'ALHE.TA',   # Alony Hetz
        'ELAL.TA',   # El Al Airlines
        'PRCH.TA',   # Perrigo
        'FTAL.TA',   # Formula Systems
        'MGRM.TA',   # Migdal Insurance
        'BIGT.TA',   # Big Shopping Centers
        'ENLT.TA',   # Energix
    ]

# ============================================================================
# GERMANY - XETRA/FRANKFURT
# ============================================================================

def get_dax_tickers():
    """
    DAX 40 tickers (.DE suffix for XETRA/Frankfurt)
    
    Last cleaned: January 2026 (removed 1 delisted stock)
    Check for updates at: https://www.dax-indices.com/
    """
    return [
        # Large-cap industrials & auto
        'SAP.DE',    # SAP
        'SIE.DE',    # Siemens
        'ALV.DE',    # Allianz
        'DTE.DE',    # Deutsche Telekom
        'BAS.DE',    # BASF
        'VOW3.DE',   # Volkswagen
        'BMW.DE',    # BMW
        'MBG.DE',    # Mercedes-Benz
        'ADS.DE',    # Adidas
        'PUM.DE',    # Puma
        
        # Financials
        'DBK.DE',    # Deutsche Bank
        'CBK.DE',    # Commerzbank
        'DB1.DE',    # Deutsche Börse
        
        # Pharma & Healthcare
        'BAYN.DE',   # Bayer
        'MRK.DE',    # Merck
        'FME.DE',    # Fresenius Medical Care
        'FRE.DE',    # Fresenius
        
        # Industrial & Tech
        'IFX.DE',    # Infineon
        'SY1.DE',    # Symrise
        'AIR.DE',    # Airbus
        'MTX.DE',    # MTU Aero Engines
        'RHM.DE',    # Rheinmetall
        'SRT.DE',    # Sartorius
        'HEI.DE',    # HeidelbergCement
        'BEI.DE',    # Beiersdorf
        
        # Energy & Utilities
        'EOAN.DE',   # E.ON
        'RWE.DE',    # RWE
        
        # Other major components
        'BNR.DE', 'CON.DE', 'DHL.DE', 'HEN.DE', 'HFG.DE',
        'MUV2.DE', 'PAH3.DE', 'QIA.DE', 'SHL.DE', 'VNA.DE',
        'ZAL.DE', 'HNR1.DE'
    ]

# ============================================================================
# MASTER FUNCTION - COMBINES ALL TICKERS
# ============================================================================

def get_all_tickers():
    """
    Combine all market tickers with fallen angel candidates prioritized
    
    Scanning order:
    1. Fallen angel candidates (most likely to have big drops)
    2. S&P 500 stocks
    3. NASDAQ-100 stocks
    4. International markets (WSE, LSE, TASE, DAX)
    """
    all_tickers = []
    
    # Add high-priority fallen angel candidates FIRST
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
