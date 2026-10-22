"""Point-in-time scan coverage; incomplete scans and source gaps stay visible."""

from datetime import datetime, timezone
import json
from pathlib import Path


def new_coverage(tickers):
    return {"started_at": datetime.now(timezone.utc).isoformat(), "completed": False,
            "requested_symbols": list(tickers), "requested_count": len(tickers), "processed_count": 0,
            "quote_successes": 0, "histories_checked": 0, "outcomes": {}, "data_gaps": [],
            "notice": "Configured/fallback universe only, not every listed company. Missing data and unverified prices do not establish that a stock failed the investment criteria."}


def record_outcome(coverage, ticker, outcome, stage, error_type=None):
    coverage["processed_count"] += 1
    coverage["last_symbol"] = ticker
    coverage["outcomes"][outcome] = coverage["outcomes"].get(outcome, 0) + 1
    if outcome in {"quote_unavailable", "data_error", "currency_unverified", "insufficient_history"}:
        coverage["data_gaps"].append({"ticker": ticker, "stage": stage, "outcome": outcome, "error_type": error_type})


def checkpoint(coverage, report_prefix):
    coverage["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = Path(report_prefix).with_name("scan_coverage.json")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(coverage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
