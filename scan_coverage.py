"""Point-in-time scan coverage; incomplete scans and source gaps stay visible."""

from datetime import datetime, timezone
import json
from pathlib import Path

MAX_CONSECUTIVE_QUOTE_FAILURES = 10


def new_coverage(tickers):
    return {"started_at": datetime.now(timezone.utc).isoformat(), "completed": False,
            "requested_symbols": list(tickers), "requested_count": len(tickers), "processed_count": 0,
            "quote_successes": 0, "histories_checked": 0, "outcomes": {}, "data_gaps": [],
            "notice": "Configured/fallback universe only, not every listed company. Missing data and unverified prices do not establish that a stock failed the investment criteria."}


def record_outcome(coverage, ticker, outcome, stage, error_type=None):
    coverage["processed_count"] += 1
    coverage["last_symbol"] = ticker
    coverage["outcomes"][outcome] = coverage["outcomes"].get(outcome, 0) + 1
    quote_failed = stage == "quote" and outcome in {"quote_unavailable", "data_error", "currency_unverified"}
    streak = coverage.get("consecutive_quote_failures", 0) + 1 if quote_failed else 0
    coverage["consecutive_quote_failures"] = streak
    coverage["maximum_consecutive_quote_failures"] = max(streak, coverage.get("maximum_consecutive_quote_failures", 0))
    if outcome in {"quote_unavailable", "data_error", "currency_unverified", "insufficient_history"}:
        coverage["data_gaps"].append({"ticker": ticker, "stage": stage, "outcome": outcome, "error_type": error_type})


def checkpoint(coverage, report_prefix):
    coverage["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = Path(report_prefix).with_name("scan_coverage.json")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(coverage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def provider_health(coverage=None, audit=None):
    """Operational source coverage, never an investment-quality assessment."""
    coverage = coverage or {}
    processed = coverage.get("processed_count", 0)
    gaps = len(coverage.get("data_gaps", []))
    errors = sum(item.get("decision") == "analysis_error" for item in (audit or []))
    count = len(audit or [])
    quote_streak = coverage.get("maximum_consecutive_quote_failures", 0)
    systemic = ((processed >= 10 and gaps * 2 >= processed)
                or quote_streak >= MAX_CONSECUTIVE_QUOTE_FAILURES
                or (count >= 10 and errors * 2 >= count))
    return {"status": "DEGRADED" if gaps or errors else "NO_RECORDED_SOURCE_ERRORS",
            "price_symbols_processed": processed, "recorded_price_source_gaps": gaps,
            "company_candidates": count, "company_analysis_errors": errors,
            "maximum_consecutive_quote_failures": quote_streak,
            "systemic_failure": systemic,
            "notice": "A source gap is not a failed investment criterion. At least 50% source failures in 10 or more observations, or 10 consecutive quote-source failures, abort normal mail/paper output. Other unverified evidence and combined price/liquidity outcomes remain in their individual decisions."}
