from datetime import date

import pytest

from backtest_data import instant
from edgar_vintages import audit_issuer, extract_vintages
from sec_filings import SecClient, SourceUnavailable


CIK = "0000001234"
BASE = "0000001234-23-000001"
AMEND = "0000001234-23-000002"
EVENT = "0000001234-23-000003"


def sources():
    block = {
        "accessionNumber": [BASE, AMEND, EVENT],
        "form": ["10-Q", "10-Q/A", "25-NSE"],
        "filingDate": ["2023-05-10", "2023-05-12", "2023-06-07"],
        "reportDate": ["2023-03-31", "2023-03-31", ""],
        "acceptanceDateTime": ["2023-05-10T21:00:00Z", "2023-05-12T21:00:00Z", "2023-06-07T13:00:00Z"],
        "primaryDocument": ["first.htm", "amendment.htm", "xslF25X02/primary_doc.xml"],
        "items": ["", "", ""],
    }
    original = dict(accn=BASE, form="10-Q", filed="2023-05-10", end="2023-03-31", val=120)
    amended = dict(accn=AMEND, form="10-Q/A", filed="2023-05-12", end="2023-03-31", val=80)
    payload = {"cik": 1234, "entityName": "Fixture", "facts": {"us-gaap": {
        "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [original, original.copy(), amended]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            {**original, "start": "2022-10-01", "val": 55}, {**original, "start": "2023-01-01", "val": 20}]}},
    }}}
    return block, payload


def extract(block, payload, asof="2023-07-01T00:00:00Z"):
    return extract_vintages(CIK, [block], payload, date(2023, 1, 1), date(2023, 6, 30), instant(asof))


def test_uses_conservative_cutoff_and_keeps_amendments_as_distinct_vintages():
    block, payload = sources()
    assert not extract(block, payload, "2023-05-11T03:59:59Z")["vintages"]
    before = extract(block, payload, "2023-05-13T03:59:59Z")
    assert [v["accession"] for v in before["vintages"]] == [BASE]
    after = extract(block, payload, "2023-05-13T04:00:00Z")
    cash = [[x["value"] for x in v["candidate_facts"] if x["category"] == "cash"] for v in after["vintages"]]
    assert cash == [[120], [80]]
    # Never sum overlapping year-to-date and quarter amounts.
    assert [x["start"] for x in before["vintages"][0]["candidate_facts"] if x["category"] == "operating_cash_flow"] == [
        "2022-10-01", "2023-01-01"]


def test_no_inferred_release_time_or_false_terminal_outcome():
    block, payload = sources()
    block["acceptanceDateTime"][0] = ""
    report = extract(block, payload)
    assert report["diagnostics"]["missing_aware_acceptance_time"] == 1
    assert [v["accession"] for v in report["vintages"]] == [AMEND]
    assert report["event_notices"][0]["form"] == "25-NSE"
    assert report["event_notices"][0]["source_url"].endswith(f"/{EVENT}-index.htm")
    assert "cash_per_share" not in report["event_notices"][0]


def test_wrong_issuer_and_metadata_conflicts_do_not_supply_facts():
    block, payload = sources()
    unit = payload["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"]["units"]["USD"]
    unit.append({**unit[0], "val": 500, "filed": "2023-05-08"})
    unit.append({**unit[0], "val": 150})
    report = extract(block, payload)
    assert report["diagnostics"]["fact_filing_metadata_conflict"] == 1
    assert report["vintages"][0]["ambiguous_groups"] == ["cash"]
    payload["cik"] = 5678
    with pytest.raises(ValueError, match="does not match"):
        extract(block, payload)


def test_audit_fetches_only_matching_archive_and_exact_sec_endpoints():
    block, payload = sources()
    calls = []
    class Client:
        def get_json(self, url):
            calls.append(url)
            if "/companyfacts/" in url:
                return payload, None
            if "-submissions-" in url:
                return block, None
            return {"cik": CIK, "filings": {"recent": {k: [] for k in block}, "files": [
                dict(name=f"CIK{CIK}-submissions-001.json", filingFrom="2023-01-01", filingTo="2023-06-30"),
                dict(name=f"CIK{CIK}-submissions-002.json", filingFrom="2019-01-01", filingTo="2019-12-31"),
            ]}}, None
    r = audit_issuer(CIK, date(2023, 1, 1), date(2023, 6, 30), instant("2023-07-01T00:00Z"), Client())
    assert len(calls) == 3 and calls == r["input_urls"]
    assert calls[-1] == f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json"
    with pytest.raises(SourceUnavailable, match="Unrecognized SEC endpoint"):
        SecClient().get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json?redirect=1")
