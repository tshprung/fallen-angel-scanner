"""Explicit quote units and timestamped, per-run cached FX for USD screening."""

from datetime import datetime, timezone
import math

import pandas as pd


class CurrencyUnavailable(ValueError):
    pass


def finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def quote_unit(code):
    # Preserve case: GBp means pence; GBP means pounds.
    if code in ("GBp", "GBX"):
        return "GBP", .01
    if code in ("ILA", "ILa"):
        return "ILS", .01
    code = str(code or "").upper()
    if code not in {"USD", "GBP", "EUR", "PLN", "ILS", "CHF", "CAD", "AUD", "JPY"}:
        raise CurrencyUnavailable(f"Unknown/missing currency: {code!r}")
    return code, 1.0


def yahoo_fx_history(pair):
    import yfinance as yf
    return yf.Ticker(pair).history(period="1mo", auto_adjust=False)


class FxRates:
    def __init__(self, loader=yahoo_fx_history, now=None):
        self.loader = loader
        self.now = pd.Timestamp(now or datetime.now(timezone.utc))
        if self.now.tzinfo is None:
            self.now = self.now.tz_localize("UTC")
        self.cache = {}

    def rate(self, currency):
        currency, scale = quote_unit(currency)
        if currency == "USD":
            return 1.0, self.now.isoformat()
        if currency not in self.cache:
            try:
                history = self.loader(f"{currency}USD=X")
                close = pd.to_numeric(history["Close"], errors="coerce")
                dates = pd.to_datetime(close.index, utc=True)
                valid = close.map(lambda v: math.isfinite(v) and v > 0)
                valid &= (dates <= self.now) & (dates >= self.now - pd.Timedelta(days=7))
                close = close[valid].sort_index()
                if close.empty:
                    raise ValueError("No valid FX observation in the last seven days")
                self.cache[currency] = (float(close.iloc[-1]), pd.Timestamp(close.index[-1]).isoformat())
            except Exception as exc:
                self.cache[currency] = CurrencyUnavailable(f"FX unavailable for {currency}: {exc}")
        result = self.cache[currency]
        if isinstance(result, Exception):
            raise result
        return result


FX = FxRates()


def currency_context(info, fx=None):
    fx = fx or FX
    code, scale = quote_unit(info.get("currency"))
    rate, asof = fx.rate(code)
    return {"quote_currency": info["currency"], "major_currency": code,
            "quote_unit_scale": scale, "quote_to_usd": scale * rate,
            "major_to_usd": rate, "fx_asof": asof}


def market_cap_usd(info, context):
    cap = finite(info.get("marketCap"))
    if cap is None or cap <= 0:
        raise CurrencyUnavailable("Missing/invalid market capitalization")
    if context["quote_unit_scale"] != 1:
        # Provider market-cap units are not consistently documented for minor
        # quotes. Resolve them against shares * quote price instead of guessing.
        shares = finite(info.get("sharesOutstanding"))
        price = finite(info.get("regularMarketPrice") or info.get("currentPrice"))
        if shares is None or shares <= 0 or price is None or price <= 0:
            raise CurrencyUnavailable("Cannot verify minor-unit market cap without shares and quote price")
        expected_major = shares * price * context["quote_unit_scale"]
        if .65 <= cap / expected_major <= 1.35:
            pass  # market cap already in major currency
        elif .65 <= cap * context["quote_unit_scale"] / expected_major <= 1.35:
            cap *= context["quote_unit_scale"]
        else:
            raise CurrencyUnavailable("Market cap and shares/quote price disagree on units")
    return cap * context["major_to_usd"]


FINANCIAL_FIELDS = ("totalDebt", "totalCash", "totalStockholderEquity", "ebitda")


def leverage_info_usd(info, context, fx=None):
    fx = fx or FX
    currency, scale = quote_unit(info.get("financialCurrency"))
    if scale != 1:
        raise CurrencyUnavailable("Financial statements must use a major currency")
    rate, asof = fx.rate(currency)
    normalized = dict(info, marketCap=market_cap_usd(info, context))
    for field in FINANCIAL_FIELDS:
        value = finite(info.get(field))
        normalized[field] = value * rate if value is not None else None
    normalized["_financial_to_usd"] = rate
    normalized["_financial_fx_asof"] = asof
    return normalized


def normalize_health(health, normalized_info):
    if health is None:
        return None
    result = dict(health)
    rate = normalized_info["_financial_to_usd"]
    for field in ("cash", "revenue", "total_debt", "net_debt"):
        value = finite(result.get(field))
        result[field] = value * rate if value is not None else 0.0
    result["market_cap"] = normalized_info["marketCap"]
    result["monetary_currency"] = "USD"
    result["financial_fx_asof"] = normalized_info["_financial_fx_asof"]
    return result
