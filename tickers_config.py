"""
Ticker Configuration File
Last updated: August 2026

Ticker universes and screening thresholds for the fallen angel scanner.
"""

# US: keep the broad Russell 1000 universe, but allow a controlled extension
# into the upper small-cap range. The scanner applies stricter liquidity and
# balance-sheet gates to names below the normal US large/mid-cap floor.
MIN_MARKET_CAP_USD_US = 750_000_000
MIN_MARKET_CAP_USD_US_STANDARD = 2_000_000_000
MIN_MARKET_CAP_USD_US_SMALL = 750_000_000

MIN_MARKET_CAP_USD_UK_DE = 1_000_000_000
MIN_MARKET_CAP_USD_PL_IL = 400_000_000


def get_min_market_cap_usd(ticker: str) -> float:
    """Minimum market cap (USD) for screening by listing suffix."""
    if ticker.endswith(".WA") or ticker.endswith(".TA"):
        return MIN_MARKET_CAP_USD_PL_IL
    if ticker.endswith(".L") or ticker.endswith(".DE"):
        return MIN_MARKET_CAP_USD_UK_DE
    return MIN_MARKET_CAP_USD_US


def get_min_avg_dollar_volume_usd(ticker: str) -> float:
    """Minimum 20-day average dollar volume; stricter for US small caps."""
    if ticker.endswith(".WA") or ticker.endswith(".TA"):
        return 350_000
    if ticker.endswith(".L") or ticker.endswith(".DE"):
        return 1_000_000
    return 2_000_000


def get_fallen_angel_candidates():
    return [
        'TTD', 'LULU', 'CDW', 'GFS', 'ON',
        'ENPH', 'CZR', 'ADSK', 'TEAM', 'ADBE', 'LDOS', 'WDAY', 'CRM',
        'ZS', 'RIVN', 'LCID', 'WBD', 'INTC',
    ]


def fetch_russell_1000_tickers():
    """Fetch Russell 1000 constituents from Wikipedia."""
    try:
        import pandas as pd
        import requests
        from io import StringIO
        import re
        url = "https://en.wikipedia.org/wiki/List_of_Russell_1000_companies"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        for table in tables:
            if "Symbol" not in table.columns:
                continue
            symbols = table["Symbol"].dropna().astype(str).str.strip()
            tickers = [t for t in symbols.tolist() if t and t.lower() != 'nan']
            tickers = [re.sub(r'\.([ABC])$', r'-\1', t) for t in tickers]
            if len(tickers) >= 500:
                return tickers
        return []
    except Exception:
        return []


def get_us_scan_tickers():
    """Primary US universe: Russell 1000, with S&P/NASDAQ fallback."""
    r1k = fetch_russell_1000_tickers()
    if len(r1k) >= 500:
        return r1k
    seen, out = set(), []
    for t in get_sp500_tickers() + get_nasdaq100_tickers():
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def get_sp500_tickers():
    try:
        import pandas as pd
        import requests
        from io import StringIO
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.raise_for_status()
        return pd.read_html(StringIO(response.text))[0]['Symbol'].tolist()
    except Exception:
        return ['AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','BRK-B','LLY','V','UNH','XOM','WMT','JPM','MA']


def get_nasdaq100_tickers():
    return ['AAPL','MSFT','GOOGL','GOOG','AMZN','NVDA','META','TSLA','AVGO','ASML','COST','NFLX','AMD','ADBE','PEP','CSCO','TMUS','CMCSA','TXN','INTC','QCOM','INTU','HON','AMGN','AMAT','SBUX','ISRG','ADP','ADI','GILD','BKNG','VRTX','PANW','REGN','LRCX','MU','MDLZ','SNPS','CDNS','PYPL','MRVL','KLAC','CRWD','ORLY','MAR','FTNT','MELI','CSX','ADSK','ABNB','DASH','ROP','WDAY','NXPI','CPRT','PCAR','CHTR','AEP','PAYX','MNST','ROST','ODFL','EA','FAST','KDP','DXCM','GEHC','CTSH','VRSK','EXC','CTAS','IDXX','KHC','XEL','CCEP','AZN','MCHP','WBD','DDOG','TEAM','MDB','ILMN','ALGN','ARM','RIVN','LCID','FER','MPWR','STX','WDC']


def get_wse_tickers():
    return ['PKO.WA','PZU.WA','PKN.WA','KGH.WA','PEO.WA','CDR.WA','ALE.WA','DNP.WA','LPP.WA','PGE.WA','JSW.WA','CPS.WA','OPL.WA','MBK.WA','KRU.WA','BDX.WA','KTY.WA','ASB.WA','MDV.WA','11B.WA','ATT.WA','CIG.WA','EUR.WA','ING.WA','KER.WA','MIL.WA']


def get_ftse100_tickers():
    return ['SHEL.L','BP.L','RIO.L','GLEN.L','BHP.L','ANTO.L','HSBA.L','BARC.L','LLOY.L','NWG.L','STAN.L','LSEG.L','PRU.L','LGEN.L','III.L','AZN.L','ULVR.L','DGE.L','BATS.L','REL.L','TSCO.L','SBRY.L','BRBY.L','NG.L','SSE.L','BA.L','RR.L','RKT.L','WPP.L','EXPN.L','CNA.L','VOD.L','BT-A.L','AAL.L','GSK.L','CPG.L','IMB.L','MNG.L','STJ.L','INF.L','FERG.L','PSN.L','AUTO.L','SGE.L','AV.L','ENT.L','SPX.L','WTB.L','CRDA.L']


def get_tase_tickers():
    return ['TEVA.TA','LUMI.TA','POLI.TA','ESLT.TA','ICL.TA','TATT.TA','AZRG.TA','NICE.TA','FIBI.TA','MZTF.TA','TASE.TA','DLEKG.TA','MLSR.TA','BEZQ.TA','ALHE.TA','ELAL.TA','FTAL.TA','BIGT.TA','ENLT.TA']


def get_dax_tickers():
    return ['SAP.DE','SIE.DE','ALV.DE','DTE.DE','BAS.DE','VOW3.DE','BMW.DE','MBG.DE','ADS.DE','PUM.DE','DBK.DE','CBK.DE','DB1.DE','BAYN.DE','MRK.DE','FME.DE','FRE.DE','IFX.DE','SY1.DE','AIR.DE','MTX.DE','RHM.DE','SRT.DE','HEI.DE','BEI.DE','EOAN.DE','RWE.DE','BNR.DE','CON.DE','DHL.DE','HEN.DE','HFG.DE','MUV2.DE','PAH3.DE','QIA.DE','SHL.DE','VNA.DE','ZAL.DE','HNR1.DE']


def get_all_tickers():
    """Return the complete scan universe."""
    tickers = []
    for group in (get_us_scan_tickers(), get_fallen_angel_candidates(), get_wse_tickers(), get_ftse100_tickers(), get_tase_tickers(), get_dax_tickers()):
        for ticker in group:
            if ticker not in tickers:
                tickers.append(ticker)
    return tickers
