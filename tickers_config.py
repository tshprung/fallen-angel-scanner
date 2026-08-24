"""
Ticker Configuration File
Last updated: August 2026

This file contains all stock ticker lists for the fallen angel scanner.
"""

# US market-cap floor. Russell 1000 + Russell 2000 together give the scanner
# a broad US universe; this floor removes the smallest/noisiest names in Stage 1.
MIN_MARKET_CAP_USD_US = 750_000_000
MIN_MARKET_CAP_USD_UK_DE = 1_000_000_000
MIN_MARKET_CAP_USD_PL_IL = 400_000_000


def get_min_market_cap_usd(ticker: str) -> float:
    if ticker.endswith(".WA") or ticker.endswith(".TA"):
        return MIN_MARKET_CAP_USD_PL_IL
    if ticker.endswith(".L") or ticker.endswith(".DE"):
        return MIN_MARKET_CAP_USD_UK_DE
    return MIN_MARKET_CAP_USD_US


def get_min_avg_dollar_volume_usd(ticker: str) -> float:
    if ticker.endswith(".WA") or ticker.endswith(".TA"):
        return 350_000
    if ticker.endswith(".L") or ticker.endswith(".DE"):
        return 1_000_000
    # Keep the same US liquidity gate for all US names. This is important now
    # that the universe includes Russell 2000 names as well.
    return 1_500_000


def get_fallen_angel_candidates():
    return [
        'TTD', 'LULU', 'CDW', 'GFS', 'ON',
        'ENPH', 'CZR', 'ADSK', 'TEAM', 'ADBE', 'LDOS', 'WDAY', 'CRM',
        'ZS', 'RIVN', 'LCID', 'WBD', 'INTC',
    ]


def _fetch_wikipedia_symbols(url):
    try:
        import pandas as pd
        import requests
        from io import StringIO
        import re
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        for table in tables:
            if "Symbol" not in table.columns:
                continue
            symbols = table["Symbol"].dropna().astype(str).str.strip()
            tickers = [t for t in symbols.tolist() if t and t.lower() != "nan"]
            return [re.sub(r'\.([ABC])$', r'-\1', t) for t in tickers]
    except Exception:
        pass
    return []


def fetch_russell_1000_tickers():
    """Fetch Russell 1000 constituents from Wikipedia."""
    tickers = _fetch_wikipedia_symbols(
        "https://en.wikipedia.org/wiki/List_of_Russell_1000_companies"
    )
    return tickers if len(tickers) >= 500 else []


def fetch_russell_2000_tickers():
    """Fetch current Russell 2000 constituents from iShares IWM holdings.

    IWM tracks the Russell 2000 and publishes its holdings as a free CSV.
    We deliberately return the full equity universe here; Stage 1's existing
    market-cap, security-type, biotech, penny-stock and liquidity filters then
    decide which names actually get analysed. This avoids introducing another
    paid market-data dependency or an extra per-ticker API call.
    """
    try:
        import csv
        import io
        import requests

        url = (
            "https://www.ishares.com/us/products/239710/"
            "ishares-russell-2000-etf/1467271812596.ajax"
            "?fileType=csv&fileName=IWM_holdings&dataType=fund"
        )
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        response.raise_for_status()
        text = response.content.decode("utf-8-sig", errors="replace")

        # iShares puts metadata lines before the actual CSV header.
        lines = text.splitlines()
        header_index = next(
            (i for i, line in enumerate(lines) if line.startswith("Ticker,")),
            None,
        )
        if header_index is None:
            return []

        reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
        tickers = []
        for row in reader:
            ticker = (row.get("Ticker") or "").strip()
            asset_class = (row.get("Asset Class") or "").strip().lower()
            if not ticker or ticker == "-":
                continue
            if asset_class and asset_class != "equity":
                continue
            # iShares can expose share classes with dots; Yahoo generally uses
            # hyphens for US share classes, matching our existing normalization.
            ticker = ticker.replace(".", "-")
            if ticker not in tickers:
                tickers.append(ticker)
        return tickers
    except Exception:
        return []


def get_us_scan_tickers():
    """Primary US universe: Russell 1000 + Russell 2000."""
    r1k = fetch_russell_1000_tickers()
    r2k = fetch_russell_2000_tickers()

    if len(r1k) >= 500 and len(r2k) >= 1000:
        combined = r1k + r2k
    elif len(r1k) >= 500:
        combined = r1k
    else:
        combined = get_sp500_tickers() + get_nasdaq100_tickers()
        if len(r2k) >= 1000:
            combined += r2k

    seen = set()
    return [t for t in combined if not (t in seen or seen.add(t))]


def get_sp500_tickers():
    tickers = _fetch_wikipedia_symbols(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    )
    return tickers or ['AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','BRK-B','LLY','V','UNH','XOM','WMT','JPM','MA']


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


def get_market_info(ticker):
    if ticker.endswith('.WA'): return "🇵🇱 WSE", "PLN"
    if ticker.endswith('.L'): return "🇬🇧 LSE", "GBP"
    if ticker.endswith('.TA'): return "🇮🇱 TASE", "ILS"
    if ticker.endswith('.DE'): return "🇩🇪 XETRA", "EUR"
    return "🇺🇸 US", "USD"


def get_all_tickers():
    all_tickers = []
    all_tickers.extend(get_fallen_angel_candidates())
    all_tickers.extend(get_us_scan_tickers())
    all_tickers.extend(get_wse_tickers())
    all_tickers.extend(get_ftse100_tickers())
    all_tickers.extend(get_tase_tickers())
    all_tickers.extend(get_dax_tickers())
    seen = set()
    unique_tickers = []
    for ticker in all_tickers:
        if ticker not in seen:
            seen.add(ticker)
            unique_tickers.append(ticker)
    return unique_tickers
