"""Production entry point with final report consistency patches."""

import fallen_angel_scanner as scanner
import scanner_bugfixes as bugfixes
import scanner_enhanced  # noqa: F401 - installs enhanced scanner patches
import scanner_safety  # noqa: F401 - installs final financial-risk guards


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


def run_cli():
    import argparse
    import sys
    from pathlib import Path
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Fallen Angel research scanner")
    parser.add_argument("--no-email", action="store_true", help="Generate reports without sending email")
    parser.add_argument("--no-paper", action="store_true", help="Do not append selections to the paper ledger")
    parser.add_argument("--tickers", help="Optional comma-separated subset instead of the full universe")
    parser.add_argument("--output-dir", help="Directory for reports and run state")
    args = parser.parse_args()
    scanner.REPORT_SCOPE = {"type": "configured_universe", "email_disabled": args.no_email,
                            "paper_disabled": args.no_paper}
    if args.no_email:
        scanner.send_email = lambda *unused: False
        scanner.check_price_alerts = lambda memory: []
    if args.no_paper:
        scanner.PAPER_TRACKING_ENABLED = False
    if args.output_dir:
        directory = Path(args.output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        scanner.REPORT_PREFIX = str(directory / "research_report")
        scanner.PAPER_LEDGER_PATH = str(directory / "paper_tracking.json")
        scanner.MEMORY_FILE = str(directory / "scanner_memory.json")
        scanner.FAILED_TICKER_FILE = str(directory / "failed_tickers.json")
    if args.tickers:
        tickers = list(dict.fromkeys(value.strip().upper() for value in args.tickers.split(",") if value.strip()))
        if not tickers:
            parser.error("--tickers must contain at least one ticker")
        scanner.get_all_tickers = lambda: tickers
        scanner.REPORT_SCOPE.update(type="subset", symbols=tickers)
        # Conservative subset floor without downloading an index merely to
        # determine whether a supplied US ticker belongs to the small-cap set.
        original_liquidity = scanner.get_min_avg_dollar_volume_usd
        scanner.get_min_avg_dollar_volume_usd = lambda ticker: original_liquidity(ticker) if ticker.endswith((".L", ".DE", ".WA", ".TA")) else 2_000_000
    scanner.main()


if __name__ == "__main__":
    run_cli()
