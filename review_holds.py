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
        known_sources = {(source["url"], source["published_at"]) for source in record["sources"]}
        for note in record.get("review_notes", []):
            if (not isinstance(note.get("finding"), str) or not note["finding"].strip()
                    or (note.get("source_url"), note.get("published_at")) not in known_sources):
                raise ValueError(f"Review note needs a matching dated source: {ticker}")
        if record["status"] == "RESOLVED" and not record.get("resolution"):
            raise ValueError(f"Resolution evidence required: {ticker}")
    return {ticker: record for ticker, record in records.items() if record["status"] == "PENDING"}
