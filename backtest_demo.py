"""Generate deliberately synthetic fixtures and a lock; never fetches market data."""

from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import sys

import pandas as pd

from backtest import DEFAULTS, lock_for, write_new
from fundamental_analysis import POLICY_PATH


def snapshot(period, weak=False):
    period = pd.Timestamp(period)
    asof = str(period.date())
    return {
        "balance": {"basis": "quarterly", "asof": asof, "values": {
            "cash": 180e6, "debt": 100e6, "current_debt": 20e6, "equity": 500e6,
            "current_assets": 350e6, "current_liabilities": 150e6}},
        "cashflow": {"basis": "ttm_quarterly", "asof": asof, "values": {"ocf": 180e6, "fcf": 120e6}},
        "income": {"basis": "ttm_quarterly", "asof": asof, "values": {
            "ebit": 20e6 if weak else 120e6, "interest": 60e6 if weak else 4e6,
            "ebitda": 160e6, "revenue": 950e6}},
        "annual_fcf": [{"asof": f"{year}-12-31", "fcf": 120e6}
                       for year in range(period.year - 1, period.year - 4, -1)],
        "annual_share_growth": 0.,
    }


def generate(output):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    dates = [stamp.date() for stamp in pd.bdate_range("2010-01-01", "2019-12-31")]
    sessions = [dict(date=str(day), open_at=f"{day}T14:30:00Z", close_at=f"{day}T21:00:00Z") for day in dates]
    symbols = ("RECOVERY", "WEAK", "VALUE", "PEER", "MARKET")
    data = dict(version=1, kind="synthetic", source="Generated fictional US sessions and prices, not market observations",
                benchmark_security_id="MARKET", sessions=sessions, securities=[], membership=[], facts=[], bars=[], actions=[])
    for sid in symbols:
        market = sid == "MARKET"
        data["securities"].append(dict(security_id=sid, issuer_id=sid, currency="USD", kind="benchmark" if market else "ordinary"))
        if not market:
            data["membership"].append(dict(security_id=sid, session=str(dates[0]), active=True, ticker=sid,
                                           available_at=f"{dates[0]}T13:00:00Z", source_id=f"synthetic-membership-{sid}"))
        for i, day in enumerate(dates):
            phase = i % 260
            crash = 100. if phase < 85 else min(100., 60.+(phase-85)*.32)
            price = (100.+i*.02 if market else crash if sid in {"RECOVERY", "WEAK"} else 62. if sid == "VALUE" else 68.)
            data["bars"].append(dict(security_id=sid, session=str(day), open=price, close=price, volume=5_000_000))
            if not market and i % 60 == 0:
                period = day-timedelta(days=7)
                data["facts"].append(dict(security_id=sid, period_end=str(period), available_at=f"{day}T20:00:00Z",
                                          source_id=f"synthetic-statement-{sid}-{day}", sector="Industrials",
                                          industry="Industrial Machinery", shares_outstanding=20_000_000,
                                          filing_status="METADATA_CHECKED", event_hold=False, evidence=snapshot(period, sid == "WEAK")))
    cfg = deepcopy(DEFAULTS)
    cfg["folds"] = {
        "development": {"start": "2011-01-03", "end": "2013-12-31"},
        "validation": {"start": "2014-01-02", "end": "2016-12-30"},
        "holdout": {"start": "2017-01-03", "end": "2019-12-31"},
    }
    write_new(out/"dataset.json", data)
    write_new(out/"protocol.json", cfg)
    write_new(out/"lock.json", lock_for(out/"dataset.json", out/"protocol.json", POLICY_PATH))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python backtest_demo.py NEW_OUTPUT_DIRECTORY")
    generate(sys.argv[1])
