"""Production entry point with final report consistency patches."""

import fallen_angel_scanner as scanner
import scanner_bugfixes as bugfixes
import scanner_enhanced  # noqa: F401 - installs enhanced scanner patches
import scanner_safety  # noqa: F401 - installs final financial-risk guards
from research_reporting import filing_review_summary_html, decision_summary_html
from disclosure_watch import summary_html as disclosure_summary_html


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
    selected = list(analyzed_stocks or []) + list(fresh_crash_stocks or [])
    documented = sum((stock.get("goal_fit") or {}).get("status") == "DOCUMENTED_12M_CASE" for stock in selected)
    minimum_upside = scanner.load_policy()["minimum_bull_upside_pct"]
    goal_summary = (f"<h2>Twelve-month recovery research</h2><p>{documented} documented conditional recovery cases; "
                    f"{len(selected) - documented} research watches. Goal: a recent meaningful decline, a financially resilient business, "
                    f"and a sourced recovery case supporting at least +{minimum_upside:g}% within a year. Neither return nor continued listing is guaranteed.</p>")
    html = _original_generate_email_html(analyzed_stocks, price_alerts, fresh_crash_stocks)
    followup = disclosure_summary_html(getattr(scanner, "_last_disclosure_watch", None))
    audit = getattr(scanner, "_last_research_audit", [])
    summary = decision_summary_html(audit, getattr(scanner, "REPORT_SCOPE", {}))
    intro = goal_summary + summary + followup
    html = html.replace("<body>", "<body>" + intro, 1) if "<body>" in html else intro + html
    held = filing_review_summary_html(audit)
    return html.replace("</body>", held + "</body>", 1) if "</body>" in html else html + held


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
    parser.add_argument("--watch-disclosures", action="store_true",
                        help="Check configured research disclosures independently of stock selection")
    parser.add_argument("--growth-shadow", action="store_true",
                        help="Collect bounded growth-recovery research without changing selections")
    args = parser.parse_args()
    scanner.REPORT_SCOPE = {"type": "configured_universe", "email_disabled": args.no_email,
                            "paper_disabled": args.no_paper}
    scanner.GROWTH_SHADOW_ENABLED = args.growth_shadow
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
    scanner._last_disclosure_watch = None
    if args.watch_disclosures:
        from disclosure_watch import run_watch
        report_dir = Path(getattr(scanner, "REPORT_PREFIX", "research_report")).parent
        scanner._last_disclosure_watch = run_watch(report_dir)
        scanner.REPORT_SCOPE["disclosure_watch"] = scanner._last_disclosure_watch
    scanner.main()


if __name__ == "__main__":
    run_cli()
