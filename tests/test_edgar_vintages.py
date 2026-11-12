from datetime import date
import json
import sys

import pytest

from backtest_data import instant
from edgar_vintages import audit_issuer, extract_vintages, main
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


def test_comparative_cash_flow_keeps_its_period_and_publication_vintage():
    block, payload = sources()
    cash_flows = payload["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"]
    cash_flows.append({**cash_flows[1], "start": "2022-01-01", "end": "2022-03-31", "val": 15})
    assert not extract(block, payload, "2023-05-11T03:59:59Z")["vintages"]
    vintage = extract(block, payload, "2023-05-11T04:00:00Z")["vintages"][0]
    assert [row["end"] for row in vintage["candidate_facts"]] == ["2023-03-31"] * 3
    assert [(row["start"], row["end"], row["value"]) for row in vintage["comparative_facts"]] == [
        ("2022-01-01", "2022-03-31", 15)]


def test_no_inferred_release_time_or_false_terminal_outcome():
    block, payload = sources()
    block["acceptanceDateTime"][0] = ""
    report = extract(block, payload)
    assert report["diagnostics"]["missing_aware_acceptance_time"] == 1
    assert [v["accession"] for v in report["vintages"]] == [AMEND]
    assert report["event_notices"][0]["form"] == "25-NSE"
    assert report["event_notices"][0]["source_url"].endswith(f"/{EVENT}-index.htm")
    assert "cash_per_share" not in report["event_notices"][0]


def test_reports_merger_proxy_and_nonreliance_only_after_availability():
    block, payload = sources()
    block["form"] = ["DEFM14A", "8-K", "8-K"]
    block["items"] = ["", "1.01,3.02,4.02", "2.02"]
    before = extract(block, payload, "2023-05-13T03:59:59Z")
    assert [event["form"] for event in before["event_notices"]] == ["DEFM14A"]
    after = extract(block, payload)
    assert [event["items"] for event in after["event_notices"]] == [[], ["1.01", "3.02", "4.02"]]


def test_cohort_audit_preserves_available_facts_when_one_issuer_is_unreachable(monkeypatch, tmp_path):
    output = tmp_path / "cohort.json"
    block, payload = sources()

    def audit(cik, start, end, asof, client):
        if cik == "5678":
            raise SourceUnavailable("SEC HTTP 403")
        return extract(block, payload)

    monkeypatch.setattr("edgar_vintages.audit_issuer", audit)
    monkeypatch.setattr(sys, "argv", ["edgar_vintages.py", "--cik", "1234", "--cik", "5678",
                                       "--start", "2020-01-01", "--end", "2023-06-30",
                                       "--as-of", "2023-07-01T00:00:00Z", "--output", str(output)])
    assert main() == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["results"][0]["cik"] == CIK
    assert report["unavailable"] == [{"cik": "0000005678", "reason": "SEC HTTP 403"}]


def test_keeps_cover_page_shares_at_their_own_date_only_after_the_filing():
    block, payload = sources()
    cover = dict(accn=BASE, form="10-Q", filed="2023-05-10", end="2023-05-08", val=33_286_190)
    payload["facts"]["dei"] = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        cover,
        {**cover, "end": "2023-05-11", "val": 166_430_950},
        {**cover, "start": "2023-03-31", "val": 200},
        {**cover, "end": "2022-12-31", "val": 100},
    ]}}}
    payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"] = {"units": {"shares": [
        {**cover, "end": "2023-03-31", "val": 33_300_000},
        {**cover, "val": 900},
    ]}}
    assert not extract(block, payload, "2023-05-11T03:59:59Z")["vintages"]
    vintage = extract(block, payload, "2023-05-11T04:00:00Z")["vintages"][0]
    shares = [(f["tag"], f["end"], f["value"]) for f in vintage["candidate_facts"] if f["unit"] == "shares"]
    assert vintage["report_period"] == "2023-03-31"
    assert shares == [
        ("dei:EntityCommonStockSharesOutstanding", "2023-05-08", 33_286_190),
        ("us-gaap:CommonStockSharesOutstanding", "2023-03-31", 33_300_000),
    ]


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
