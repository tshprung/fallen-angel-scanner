"""Sourced manual review holds; absence is not comprehensive event clearance."""

import json
from pathlib import Path


def load_review_holds(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name("review_holds.json")
    records = json.loads(path.read_text(encoding="utf-8"))
    for ticker, record in records.items():
        if (ticker != ticker.upper() or record.get("status") not in {"PENDING", "RESOLVED"}
                or not record.get("reason") or not record.get("release_condition")
                or not record.get("reviewed_at") or not record.get("sources")):
            raise ValueError(f"Incomplete review hold: {ticker}")
        for source in record["sources"]:
            if not source.get("url", "").startswith("https://") or not source.get("published_at"):
                raise ValueError(f"Incomplete review source: {ticker}")
        if record["status"] == "RESOLVED" and not record.get("resolution"):
            raise ValueError(f"Resolution evidence required: {ticker}")
    return {ticker: record for ticker, record in records.items() if record["status"] == "PENDING"}
