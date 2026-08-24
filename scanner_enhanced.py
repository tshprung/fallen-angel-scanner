"""Enhanced daily runner for the fallen-angel scanner.

Adds two things on top of scanner_policy.py:
1. A small-cap quality overlay based on actual US market cap, not only index
   membership. This prevents risky small names from slipping through when an
   index membership list changes (e.g. heavily levered equity stubs).
2. An informational Trend Template / CANSLIM-style recovery score for the
   final candidates. It is deliberately NOT a gate: a fallen angel is often
   below its moving averages by definition. The score tells us whether the
   recovery has already begun.

The score is calculated only for final candidates, so it adds at most a few
extra Yahoo history requests and keeps the once-daily GitHub Action practical.
"""

import numpy as np
import yfinance as yf

import fallen_angel_scanner as scanner
import scanner_policy as policy


SMALL_CAP_MAX_MARKET_CAP_USD = 5_000_000_000
SMALL_CAP_MAX_NET_DEBT_TO_MCAP = 0.75
SMALL_CAP_MAX_DEBT_EBITDA = 5.0
SMALL_CAP_MAX_RISK_SCORE = 2
SMALL_CAP_MIN_PIOTROSKI = 4


def _is_us_small_cap(stock):
    ticker = stock.get("ticker", "")
    if any(ticker.endswith(s) for s in (".WA", ".TA", ".L", ".DE")):
        return False
    cap = stock.get("market_cap_usd") or stock.get("market_cap") or 0
    return 0 < float(cap) <= SMALL_CAP_MAX_MARKET_CAP_USD


def _apply_small_cap_quality_overlay(stocks):
    """Apply quality gates to all genuinely small US companies, not just S&P 600 members."""
    out = []
    for stock in stocks:
        if not _is_us_small_cap(stock):
            out.append(stock)
            continue

        ticker = stock["ticker"]
        health = stock.get("financial_health") or {}
        cap = float(stock.get("market_cap_usd") or stock.get("market_cap") or 0)
        risk = stock.get("risk_score")
        piotroski = stock.get("piotroski_score")
        checks = stock.get("piotroski_checks")
        debt_ebitda = health.get("debt_ebitda")
        net_debt = health.get("net_debt")

        if risk is not None and risk > SMALL_CAP_MAX_RISK_SCORE:
            print(f"  ⏭️  {ticker} removed by US small-cap quality overlay: risk {risk}/10")
            continue

        if piotroski is not None and checks is not None and checks >= 6 and piotroski < SMALL_CAP_MIN_PIOTROSKI:
            print(f"  ⏭️  {ticker} removed by US small-cap quality overlay: Piotroski F{piotroski}/{checks}")
            continue

        if debt_ebitda is not None and np.isfinite(float(debt_ebitda)) and float(debt_ebitda) > SMALL_CAP_MAX_DEBT_EBITDA:
            print(f"  ⏭️  {ticker} removed by US small-cap quality overlay: debt/EBITDA {float(debt_ebitda):.1f}x")
            continue

        if net_debt is not None and float(net_debt) > 0 and cap > 0:
            ratio = float(net_debt) / cap
            if ratio >= SMALL_CAP_MAX_NET_DEBT_TO_MCAP:
                print(f"  ⏭️  {ticker} removed by US small-cap quality overlay: net debt {ratio:.1f}x market cap")
                continue

        out.append(stock)
    return out


def _trend_template_score(ticker):
    """Return a 0-7 Minervini/CANSLIM Trend Template-style score.

    This is used as recovery confirmation, not as a fallen-angel admission gate.
    """
    try:
        close = yf.Ticker(ticker).history(period="1y", auto_adjust=False)["Close"].dropna()
        if len(close) < 210:
            return None

        price = float(close.iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma150 = float(close.rolling(150).mean().iloc[-1])
        ma200_series = close.rolling(200).mean()
        ma200 = float(ma200_series.iloc[-1])
        ma200_20d = float(ma200_series.iloc[-21])
        low_52 = float(close.min())
        high_52 = float(close.max())

        criteria = [
            price > ma150,
            price > ma200,
            ma150 > ma200,
            ma200 > ma200_20d,
            ma50 > ma150 and ma50 > ma200,
            price > ma50,
            price >= low_52 * 1.30 and price >= high_52 * 0.75,
        ]
        return sum(bool(x) for x in criteria)
    except Exception as exc:
        print(f"  ⚠️ Trend Template unavailable for {ticker}: {exc}")
        return None


def _attach_trend_scores(stocks):
    for stock in stocks:
        score = _trend_template_score(stock["ticker"])
        stock["trend_template_score"] = score
        if score is None:
            stock["trend_template_label"] = "n/a"
        elif score >= 6:
            stock["trend_template_label"] = "recovery confirmed"
        elif score >= 4:
            stock["trend_template_label"] = "transition"
        else:
            stock["trend_template_label"] = "still in bottoming phase"
    return stocks


_original_stage2 = scanner.stage2_deep_analysis


def stage2_enhanced(candidates, memory):
    analyzed, fresh = _original_stage2(candidates, memory)
    analyzed = _apply_small_cap_quality_overlay(analyzed)
    fresh = _apply_small_cap_quality_overlay(fresh)
    analyzed = _attach_trend_scores(analyzed)
    fresh = _attach_trend_scores(fresh)
    return analyzed, fresh


scanner.stage2_deep_analysis = stage2_enhanced


_original_generate_email_html = scanner.generate_email_html


def _trend_section(stocks):
    rows = []
    for stock in stocks:
        score = stock.get("trend_template_score")
        score_txt = f"{score}/7" if score is not None else "n/a"
        label = stock.get("trend_template_label", "n/a")
        rows.append(
            f"<tr><td style='padding:7px'><strong>{stock['ticker']}</strong></td>"
            f"<td style='padding:7px;text-align:center'>{score_txt}</td>"
            f"<td style='padding:7px'>{label}</td></tr>"
        )
    if not rows:
        return ""
    return """
    <h2>📈 Recovery Trend Confirmation (informational)</h2>
    <p>The Trend Template score is <strong>not a filter</strong>. A fallen angel
    near its bottom is expected to score low; the score becomes useful as the
    price starts reclaiming its moving averages.</p>
    <table style="width:100%;border-collapse:collapse;margin:15px 0">
      <tr style="background:#34495e;color:white">
        <th style="padding:7px;text-align:left">Ticker</th>
        <th style="padding:7px">Score</th>
        <th style="padding:7px;text-align:left">Interpretation</th>
      </tr>
    """ + "".join(rows) + "</table>"


def generate_email_html_enhanced(analyzed_stocks, price_alerts, fresh_crash_stocks=None):
    html = _original_generate_email_html(analyzed_stocks, price_alerts, fresh_crash_stocks)
    html += _trend_section(list(analyzed_stocks or []) + list(fresh_crash_stocks or []))
    return html


scanner.generate_email_html = generate_email_html_enhanced


if __name__ == "__main__":
    scanner.main()
