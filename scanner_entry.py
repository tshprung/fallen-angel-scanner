"""Production entry point with final report consistency patches."""

import fallen_angel_scanner as scanner
import scanner_bugfixes as bugfixes
import scanner_enhanced  # noqa: F401 - installs enhanced scanner patches


_original_generate_email_html = scanner.generate_email_html


def _apply_consistent_sentiment(stocks):
    for stock in stocks or []:
        label, reason = bugfixes._catalyst_display(stock)
        stock["news_sentiment"] = label
        stock["sentiment_reason"] = reason
    return stocks


def generate_email_html_consistent(analyzed_stocks, price_alerts, fresh_crash_stocks=None):
    _apply_consistent_sentiment(analyzed_stocks)
    _apply_consistent_sentiment(fresh_crash_stocks)
    return _original_generate_email_html(
        analyzed_stocks, price_alerts, fresh_crash_stocks
    )


scanner.generate_email_html = generate_email_html_consistent


if __name__ == "__main__":
    scanner.main()
