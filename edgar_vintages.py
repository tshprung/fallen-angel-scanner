"""Bounded public filing audit. This does not construct a tradable dataset."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import math
import re
from urllib.parse import quote
from zoneinfo import ZoneInfo

from backtest import write_new
from backtest_data import instant
from sec_filings import SecClient, SourceUnavailable


PERIODIC = {"10-Q", "10-K", "10-Q/A", "10-K/A"}
EVENTS = {"8-K", "8-K/A", "25", "25-NSE", "25/A", "25-NSE/A"}
NY = ZoneInfo("America/New_York")
# This is a candidate crosswalk, not an accounting normalization. In
# particular, never combine debt lines or sum cumulative cash-flow durations.
TAGS = {
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "equity": ("StockholdersEquity",),
    "debt_candidates": ("ShortTermBorrowings", "LongTermDebtCurrent", "LongTermDebtNoncurrent",
                        "LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtAndFinanceLeaseObligationsNoncurrent"),
    "operating_income": ("OperatingIncomeLoss",),
    "interest_candidates": ("InterestExpense", "InterestExpenseNonOperating", "InterestAndDebtExpense"),
    "revenue_candidates": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                           "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex_candidates": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
    "shares_candidates": ("CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"),
}


def conservative_cutoff(filed, accepted):
    # EDGAR acceptance is not a guaranteed public dissemination timestamp.
    # Wait until the next New York calendar day after both dates.
    after = max(filed, accepted.astimezone(NY).date()) + timedelta(days=1)
    return datetime.combine(after, time.min, NY).astimezone(timezone.utc)


def collect_filing_index(blocks, cik, start, end, asof):
    rows, counts = {}, Counter()
    required = ("accessionNumber", "form", "filingDate", "reportDate", "acceptanceDateTime", "primaryDocument")
    for block in blocks:
        if any(not isinstance(block.get(k), list) for k in required):
            raise ValueError("SEC submission index lacks required arrays")
        n = len(block["form"])
        if any(len(block[k]) != n for k in required) or len(block.get("items", [""]*n)) != n:
            raise ValueError("SEC submission arrays are misaligned")
        for i in range(n):
            acc, form, filed, period, accepted, primary = [block[k][i] for k in required]
            if form not in PERIODIC | EVENTS:
                continue
            filed = date.fromisoformat(filed)
            if not start <= filed <= end:
                continue
            if (not re.fullmatch(r"\d{10}-\d{2}-\d{6}", acc)
                    or not re.fullmatch(r"[A-Za-z0-9_.-]+", primary) or ".." in primary):
                raise ValueError("Invalid SEC accession or primary document name")
            try:
                accepted_at = instant(accepted)
            except (ValueError, AttributeError, TypeError):
                counts["missing_aware_acceptance_time"] += 1
                continue
            cutoff = conservative_cutoff(filed, accepted_at)
            if cutoff > asof:
                counts["not_available_by_cutoff"] += 1
                continue
            items = sorted(set(re.findall(r"\b\d\.\d{2}\b", block.get("items", [""]*n)[i] or "")))
            if form.startswith("8-K") and not {"1.03", "3.01", "2.01", "2.04"}.intersection(items):
                continue
            if form in PERIODIC and (not period or date.fromisoformat(period) > filed):
                counts["missing_or_invalid_report_period"] += 1
                continue
            row = dict(accession=acc, form=form, filed=str(filed), report_period=period or None,
                       accepted_at=accepted_at.isoformat(), available_at=cutoff.isoformat(), items=items,
                       source_url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{quote(primary, safe='')}")
            if acc in rows and rows[acc] != row:
                raise ValueError("Conflicting SEC submission index versions for one accession")
            rows[acc] = row
    return rows, counts


def extract_vintages(cik, blocks, companyfacts, start, end, asof):
    if int(companyfacts["cik"]) != int(cik):
        raise ValueError("Companyfacts issuer does not match requested CIK")
    filings, counts = collect_filing_index(blocks, cik, start, end, asof)
    periodic = {k: v for k, v in filings.items() if v["form"] in PERIODIC}
    facts = defaultdict(set)
    for category, tags in TAGS.items():
        for tag in tags:
            namespace = "dei" if tag == "EntityCommonStockSharesOutstanding" else "us-gaap"
            unit = "shares" if category == "shares_candidates" else "USD"
            rows = companyfacts.get("facts", {}).get(namespace, {}).get(tag, {}).get("units", {}).get(unit, [])
            for obs in rows:
                acc = obs.get("accn")
                source = periodic.get(acc)
                if source is None or obs.get("end") != source["report_period"]:
                    continue
                if obs.get("filed") != source["filed"] or obs.get("form") != source["form"]:
                    counts["fact_filing_metadata_conflict"] += 1
                    continue
                val, started = obs.get("val"), obs.get("start") or ""
                if (type(val) not in (int, float) or not math.isfinite(val)
                        or (started and date.fromisoformat(started) > date.fromisoformat(obs["end"]))):
                    counts["invalid_fact_values_or_duration"] += 1
                    continue
                facts[acc].add((category, f"{namespace}:{tag}", unit, started, obs["end"], val))
    result = []
    for acc, row in sorted(periodic.items(), key=lambda pair: (pair[1]["available_at"], pair[0])):
        values = sorted(facts[acc])
        categories = {value[0] for value in values}
        grouped = defaultdict(set)
        for category, tag, unit, start_date, end_date, value in values:
            grouped[(category, unit, start_date, end_date)].add(value)
        ambiguous = sorted({key[0] for key, vals in grouped.items() if len(vals) > 1})
        result.append({**row, "candidate_facts": [
            dict(category=k, tag=t, unit=u, start=s or None, end=e, value=v)
            for k, t, u, s, e, v in values],
            "missing_groups": sorted(set(TAGS)-categories), "ambiguous_groups": ambiguous})
    return dict(cik=str(cik).zfill(10), issuer=companyfacts.get("entityName"), vintages=result,
                event_notices=sorted((r for r in filings.values() if r["form"] not in PERIODIC),
                                     key=lambda r: (r["available_at"], r["accession"])),
                diagnostics=dict(counts))


def audit_issuer(cik, start, end, asof, client):
    if not re.fullmatch(r"\d{1,10}", cik) or not int(cik):
        raise ValueError("Expected a nonzero numeric CIK")
    cik = cik.zfill(10)
    def get(url):
        try:
            payload, _ = client.get_json(url)
        except SourceUnavailable as exc:
            raise SourceUnavailable(f"{url}: {exc}") from None
        return payload

    endpoint = f"https://data.sec.gov/submissions/CIK{cik}.json"
    metadata = get(endpoint)
    if int(metadata["cik"]) != int(cik):
        raise ValueError("Submissions issuer does not match requested CIK")
    index = metadata["filings"]
    archives = [r for r in index["files"] if date.fromisoformat(r["filingTo"]) >= start
                and date.fromisoformat(r["filingFrom"]) <= end]
    if len(archives) > 4:
        raise SourceUnavailable("Date range needs more than four archive pages; narrow the pilot")
    blocks = [index["recent"]]
    sources = [endpoint]
    for archive in archives:
        name = archive["name"]
        if not re.fullmatch(rf"CIK{cik}-submissions-\d{{3}}\.json", name):
            raise ValueError("Unexpected SEC archive identity")
        url = "https://data.sec.gov/submissions/" + name
        block = get(url)
        sources.append(url)
        blocks.append(block)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    facts = get(url)
    return {**extract_vintages(cik, blocks, facts, start, end, asof), "input_urls": [*sources, url]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cik", action="append", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        start, end, asof = date.fromisoformat(args.start), date.fromisoformat(args.end), instant(args.as_of)
        if len(args.cik) > 3 or not 0 <= (end-start).days <= 366:
            raise ValueError("Pilot limit: three issuers and at most 366 calendar days")
        client = SecClient()
        results = [audit_issuer(cik, start, end, asof, client) for cik in args.cik]
        write_new(args.output, dict(kind="edgar_vintage_audit_only", as_of=asof.isoformat(),
                                   filing_window=[str(start), str(end)], results=results,
                                   notice="No raw market data, historical membership, terminal proceeds, risk clearance or performance. "
                                          "Keep original fact dates/units; no TTM normalization or facts imported into replay."))
        for r in results:
            populated = sum(bool(row["candidate_facts"]) for row in r["vintages"])
            print(f"CIK {r['cik']}: {populated}/{len(r['vintages'])} filings with candidate facts; "
                  f"{len(r['event_notices'])} event notices; diagnostics={r['diagnostics']}")
        if any(not any(row["candidate_facts"] for row in r["vintages"]) for r in results):
            return 1
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"EDGAR pilot error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
