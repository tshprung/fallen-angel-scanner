import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.modules.setdefault("yfinance", MagicMock())

from fallen_angel_scanner import generate_email_html


def _make_stock(ticker, bucket):
    return {
        'ticker': ticker,
        'company': f'{ticker} Corp',
        'market': '🇺🇸 US',
        'currency': 'USD',
        'broker': 'Revolut',
        'alt_broker': '',
        'current_price': 100.0,
        'drop_21d_pct': -24.0,
        'drop_from_peak_pct': -24.0,
        'drop_pct': -24.0,
        'rsi': 22.0,
        'recovery_potential': 30.0,
        'target_low': 120.0,
        'target_high': 140.0,
        'risk_score': 3,
        'at_bottom': True,
        'wait_price_low': 95.0,
        'wait_price_high': 100.0,
        'bottom_confidence': 'HIGH',
        'earnings_date': None,
        'days_to_earnings': None,
        'news_headlines': ['Some headline'],
        'news_sentiment': 'Neutral',
        'sentiment_reason': 'Mixed reaction',
        'financial_health': {
            'debt_equity_display': 1.2,
            'cash': 5e9,
            'revenue_growth_yoy': 2.5,
            'net_debt': 1e9,
            'debt_ebitda': 1.5,
            'current_ratio': 1.8,
            'market_cap': 2e11,
        },
        'piotroski_score': 7,
        'piotroski_checks': {},
        'forward_pe': 15.0,
        'price_to_book': 2.0,
        'short_percent': 0.05,
        'market_cap_usd': 2e11,
        'price_shape': 'sudden_drop',
        'shape_stable_years': 1.5,
        'shape_recent_drop_pct': -24.0,
        'bucket': bucket,
    }


def test_email_renders_with_both_buckets_populated():
    fallen_angel = _make_stock('AAA', 'fallen_angel')
    fresh_crash = _make_stock('IBM', 'fresh_crash')

    html = generate_email_html([fallen_angel], [], [fresh_crash])

    assert 'AAA' in html
    assert 'IBM' in html
    assert 'Fresh Crash Watch' in html
    assert 'Fallen Angels' in html
    assert '<html>' in html and '</html>' in html


def test_email_renders_with_empty_fresh_crash_list():
    # Backward-compat: omitting fresh_crash_stocks entirely must still work
    fallen_angel = _make_stock('AAA', 'fallen_angel')
    html = generate_email_html([fallen_angel], [])
    assert 'AAA' in html
    assert 'Fresh Crash Watch' not in html


def test_email_renders_with_only_fresh_crash():
    fresh_crash = _make_stock('IBM', 'fresh_crash')
    html = generate_email_html([], [], [fresh_crash])
    assert 'IBM' in html
    assert 'Fresh Crash Watch' in html
    assert 'High-Quality Fallen Angels' not in html
