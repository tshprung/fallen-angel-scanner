"""Enhanced daily runner for the fallen-angel scanner.

Adds a quality overlay and recovery-confirmation signals while keeping the core
scanner intact. The enhanced runner also softens hard boundaries that otherwise
hide useful borderline candidates.
"""

import numpy as np
import pandas as pd
import yfinance as yf

import fallen_angel_scanner as scanner
import scanner_policy as policy
import scanner_bugfixes as bugfixes  # Production fixes: financial data, news, shape diagnostics

scanner.DEDUP_DAYS = 3
MAX_ADMISSIBLE_RISK_SCORE = 4
SMALL_CAP_MAX_MARKET_CAP_USD = 5_000_000_000
SMALL_CAP_MAX_NET_DEBT_TO_MCAP = 0.75
SMALL_CAP_MAX_DEBT_EBITDA = 5.0
SMALL_CAP_MAX_RISK_SCORE = 3
SMALL_CAP_MIN_PIOTROSKI = 4
policy.SMALL_CAP_MAX_RISK_SCORE = SMALL_CAP_MAX_RISK_SCORE

TICKER_ALIASES = {"CCC.WA": "MDV.WA"}

# ---------------------------------------------------------------------------
# Corporate-action-safe price history
# ---------------------------------------------------------------------------
_ORIGINAL_TICKER = yf.Ticker


def _split_normalize_history(hist, ticker_obj):
    if hist is None or hist.empty or "Close" not in hist.columns:
        return hist
    try:
        splits = ticker_obj.splits
        if splits is None or splits.empty:
            return hist
        out = hist.copy()
        for split_date, ratio in splits.dropna().items():
            ratio = float(ratio)
            if not np.isfinite(ratio) or ratio <= 0 or abs(ratio - 1.0) < 1e-9:
                continue
            cutoff = pd.Timestamp(split_date)
            idx = out.index
            if getattr(idx, "tz", None) is not None and cutoff.tzinfo is None:
                cutoff = cutoff.tz_localize(idx.tz)
            elif getattr(idx, "tz", None) is None and cutoff.tzinfo is not None:
                cutoff = cutoff.tz_localize(None)
            out.loc[out.index < cutoff, [c for c in out.columns if c in ("Open", "High", "Low", "Close")]] /= ratio
        return out
    except Exception:
        return hist


class _SplitSafeTicker:
    def __init__(self, ticker):
        self._ticker = _ORIGINAL_TICKER(ticker)

    def history(self, *args, **kwargs):
        kwargs = dict(kwargs)
        kwargs["auto_adjust"] = False
        hist = self._ticker.history(*args, **kwargs)
        return _split_normalize_history(hist, self._ticker)

    def __getattr__(self, name):
        return getattr(self._ticker, name)


yf.Ticker = _SplitSafeTicker


def _is_us_small_cap(stock):
    ticker = stock.get("ticker", "")
    if any(ticker.endswith(s) for s in (".WA", ".TA", ".L", ".DE")):
        return False
    cap = stock.get("market_cap_usd") or stock.get("market_cap") or 0
    return 0 < float(cap) <= SMALL_CAP_MAX_MARKET_CAP_USD


def _apply_small_cap_quality_overlay(stocks):
    out = []
    for stock in stocks:
        if not _is_us_small_cap(stock):
            out.append(stock)
            continue
        ticker = stock["ticker"]
        health = stock.get("financial_health") or {}
        cap = float(stock.get("market_cap_usd") or stock.get("market_cap") or 0)
        risk = stock.get("risk_score_raw", stock.get("risk_score"))
        piotroski = stock.get("piotroski_score")
        checks = stock.get("piotroski_checks")
        debt_ebitda = health.get("debt_ebitda")
        net_debt = health.get("net_debt")
        if risk is not None and risk > SMALL_CAP_MAX_RISK_SCORE:
            print(f"  ⏭️  {ticker} removed by US small-cap quality overlay: risk {risk}/10")
            stock["overlay_exclusion_reason"] = f"Risk {risk}/10 > {SMALL_CAP_MAX_RISK_SCORE}/10"
            continue
        if piotroski is not None and checks is not None and checks >= 6 and piotroski < SMALL_CAP_MIN_PIOTROSKI:
            print(f"  ⏭️  {ticker} removed by US small-cap quality overlay: Piotroski F{piotroski}/{checks}")
            stock["overlay_exclusion_reason"] = f"Piotroski F{piotroski}/{checks} < F{SMALL_CAP_MIN_PIOTROSKI}"
            continue
        if debt_ebitda is not None and np.isfinite(float(debt_ebitda)) and float(debt_ebitda) > SMALL_CAP_MAX_DEBT_EBITDA:
            print(f"  ⏭️  {ticker} removed by US small-cap quality overlay: debt/EBITDA {float(debt_ebitda):.1f}x")
            stock["overlay_exclusion_reason"] = f"Debt/EBITDA {float(debt_ebitda):.1f}x > {SMALL_CAP_MAX_DEBT_EBITDA:.1f}x"
            continue
        if net_debt is not None and float(net_debt) > 0 and cap > 0:
            ratio = float(net_debt) / cap
            if ratio >= SMALL_CAP_MAX_NET_DEBT_TO_MCAP:
                print(f"  ⏭️  {ticker} removed by US small-cap quality overlay: net debt {ratio:.1f}x market cap")
                stock["overlay_exclusion_reason"] = f"Net debt/market cap {ratio:.1f}x >= {SMALL_CAP_MAX_NET_DEBT_TO_MCAP:.2f}x"
                continue
        out.append(stock)
    return out


def _trend_template_score(ticker):
    try:
        close = yf.Ticker(ticker).history(period="1y")["Close"].dropna()
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
        criteria = [price > ma150, price > ma200, ma150 > ma200, ma200 > ma200_20d,
                    ma50 > ma150 and ma50 > ma200, price > ma50,
                    price >= low_52 * 1.30 and price >= high_52 * 0.75]
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


_original_calculate_risk_score = scanner.calculate_risk_score


def _calculate_risk_score_soft_gate(*args, **kwargs):
    raw = _original_calculate_risk_score(*args, **kwargs)
    if raw == 4:
        financial_health = args[0] if args else kwargs.get("financial_health")
        if isinstance(financial_health, dict):
            financial_health["_raw_risk_score"] = 4
        return 3
    return raw


scanner.calculate_risk_score = _calculate_risk_score_soft_gate


# Yahoo Finance/WSE ticker migrations are handled here because this enhanced
# runner is the production entry point. Empty histories are valid provider
# responses and must never reach iloc[-1].
def _migrate_tracked_tickers(memory):
    tracked = memory.setdefault("tracked_prices", {})
    for old_ticker, new_ticker in TICKER_ALIASES.items():
        if old_ticker in tracked:
            if new_ticker not in tracked:
                tracked[new_ticker] = tracked[old_ticker]
            del tracked[old_ticker]
            print(f"  🔄 Migrated tracked ticker {old_ticker} → {new_ticker}")
    return memory


_original_load_memory = scanner.load_memory


def _load_memory_with_migrations():
    return _migrate_tracked_tickers(_original_load_memory())


scanner.load_memory = _load_memory_with_migrations


def _safe_check_price_alerts(memory):
    alerts = []
    tracked = memory.setdefault("tracked_prices", {})
    for stored_ticker, data in list(tracked.items()):
        ticker = TICKER_ALIASES.get(stored_ticker, stored_ticker)
        if ticker != stored_ticker:
            if ticker not in tracked:
                tracked[ticker] = data
            del tracked[stored_ticker]
            data = tracked[ticker]
            print(f"  🔄 Migrated tracked ticker {stored_ticker} → {ticker}")
        try:
            stock = yf.Ticker(ticker)
            history = stock.history(period="1d")
            if history is None or history.empty or "Close" not in history.columns:
                print(f"  ⚠️  No price data for {ticker}; skipping alert check")
                continue
            closes = history["Close"].dropna()
            if closes.empty:
                print(f"  ⚠️  Empty price history for {ticker}; skipping alert check")
                continue
            current_price = float(closes.iloc[-1])
            original_price = float(data["price"])
            stored_date = data.get("date")
            try:
                splits = stock.splits
                if stored_date and splits is not None and not splits.empty:
                    split_cutoff = pd.Timestamp(stored_date)
                    if split_cutoff.tzinfo is None:
                        split_cutoff = split_cutoff.tz_localize("UTC")
                    else:
                        split_cutoff = split_cutoff.tz_convert("UTC")
                    split_index = splits.index
                    if split_index.tz is None:
                        split_index = split_index.tz_localize("UTC")
                    else:
                        split_index = split_index.tz_convert("UTC")
                    recent_splits = splits.copy()
                    recent_splits.index = split_index
                    recent_splits = recent_splits[recent_splits.index > split_cutoff]
                    if not recent_splits.empty:
                        cumulative_ratio = float(recent_splits.prod())
                        if cumulative_ratio > 0:
                            original_price /= cumulative_ratio
            except Exception:
                pass
            drop_since_alert = current_price / original_price - 1
            if drop_since_alert <= -scanner.PRICE_ALERT_THRESHOLD:
                alerts.append({"ticker": ticker, "original_price": original_price,
                               "current_price": current_price,
                               "additional_drop": drop_since_alert * 100,
                               "sent_date": data.get("date")})
        except Exception as exc:
            print(f"  ⚠️  Failed to check {ticker}: {exc}")
            continue
    return alerts


scanner.check_price_alerts = _safe_check_price_alerts

_original_stage2 = scanner.stage2_deep_analysis


def stage2_enhanced(candidates, memory):
    analyzed, fresh = _original_stage2(candidates, memory)
    core_candidates = list(analyzed) + list(fresh)
    core_count = len(core_candidates)
    for stock in core_candidates:
        health = stock.get("financial_health") or {}
        raw = health.get("_raw_risk_score")
        if raw is not None:
            stock["risk_score_raw"] = raw
            stock["risk_label"] = "WATCH (raw risk 4/10)"
        else:
            stock["risk_score_raw"] = stock.get("risk_score")
            stock["risk_label"] = "LOW RISK" if (stock.get("risk_score") or 10) <= 3 else "WATCH"
        stock.setdefault("overlay_exclusion_reason", None)

    analyzed_filtered = _apply_small_cap_quality_overlay(analyzed)
    fresh_filtered = _apply_small_cap_quality_overlay(fresh)
    survivors = len(analyzed_filtered) + len(fresh_filtered)
    filtered = [s for s in core_candidates if s.get("overlay_exclusion_reason")]
    scanner._last_core_stage2_candidates = core_candidates
    scanner._last_overlay_filtered_candidates = filtered
    print(f"  🔎 Quality overlay: {survivors}/{core_count} core candidates survived")
    if filtered:
        for stock in filtered:
            print(f"  🧾 Filtered candidate: {stock['ticker']} — {stock['overlay_exclusion_reason']}")
    analyzed = _attach_trend_scores(analyzed_filtered)
    fresh = _attach_trend_scores(fresh_filtered)
    return analyzed, fresh


scanner.stage2_deep_analysis = stage2_enhanced

_original_generate_email_html = scanner.generate_email_html


def _trend_section(stocks):
    rows = []
    for stock in stocks:
        score = stock.get("trend_template_score")
        score_txt = f"{score}/7" if score is not None else "n/a"
        label = stock.get("trend_template_label", "n/a")
        raw = stock.get("risk_score_raw")
        risk_txt = f"{raw}/10" if raw is not None else "n/a"
        admission = stock.get("risk_score")
        admission_txt = f"{admission}/10" if admission is not None else "n/a"
        rows.append(f"<tr><td style='padding:7px'><strong>{stock['ticker']}</strong></td>"
                    f"<td style='padding:7px;text-align:center'>{risk_txt}</td>"
                    f"<td style='padding:7px;text-align:center'>{admission_txt}</td>"
                    f"<td style='padding:7px;text-align:center'>{score_txt}</td>"
                    f"<td style='padding:7px'>{label}</td></tr>")
    if not rows:
        return ""
    return """
    <h2>📈 Recovery Confirmation</h2>
    <p><strong>Raw Risk</strong> is the scanner's original 1–10 score. A raw
    4/10 candidate is admitted as <strong>WATCH</strong> rather than silently
    discarded; raw risk ≥5 remains excluded. Trend Template is informational
    because a fallen angel near its bottom can legitimately score low.</p>
    <table style="width:100%;border-collapse:collapse;margin:15px 0">
      <tr style="background:#34495e;color:white">
        <th style="padding:7px;text-align:left">Ticker</th><th style="padding:7px">Raw Risk</th>
        <th style="padding:7px">Admission</th><th style="padding:7px">Trend</th>
        <th style="padding:7px;text-align:left">Interpretation</th>
      </tr>
    """ + "".join(rows) + "</table>"


def _filtered_candidates_section():
    stocks = getattr(scanner, "_last_overlay_filtered_candidates", []) or []
    if not stocks:
        return ""
    rows = []
    for stock in stocks:
        bucket = stock.get("bucket", "candidate")
        reason = stock.get("overlay_exclusion_reason", "quality overlay")
        rows.append(
            f"<tr style='border-bottom:1px solid #ddd'>"
            f"<td style='padding:7px"><strong>{stock['ticker']}</strong></td>"
            f"<td style='padding:7px'>{bucket.replace('_', ' ')}</td>"
            f"<td style='padding:7px'>{reason}</td>"
            f"</tr>"
        )
    return """
    <h2>🔎 Stage 2 Candidates Filtered by Quality Overlay</h2>
    <p>These candidates passed the core Stage 2 analysis but were removed by the
    additional US small-cap quality screen. They are shown for transparency and
    are <strong>not</strong> counted as recovery opportunities.</p>
    <table style="width:100%;border-collapse:collapse;margin:15px 0">
      <tr style="background:#7f8c8d;color:white">
        <th style="padding:7px;text-align:left">Ticker</th>
        <th style="padding:7px;text-align:left">Bucket</th>
        <th style="padding:7px;text-align:left">Reason</th>
      </tr>
    """ + "".join(rows) + "</table>"


def generate_email_html_enhanced(analyzed_stocks, price_alerts, fresh_crash_stocks=None):
    html = _original_generate_email_html(analyzed_stocks, price_alerts, fresh_crash_stocks)
    html += _filtered_candidates_section()
    html += _trend_section(list(analyzed_stocks or []) + list(fresh_crash_stocks or []))
    return html


scanner.generate_email_html = generate_email_html_enhanced

# scanner_bugfixes must remain the final news implementation: scanner_enhanced
# used to overwrite it with the legacy price-inference fallback, which is why
# the previous run still reported fabricated "likely earnings" causes.
scanner.search_recent_news = bugfixes.search_recent_news_fixed


if __name__ == "__main__":
    scanner.main()
