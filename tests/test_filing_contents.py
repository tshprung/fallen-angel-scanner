from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from filing_contents import (DocumentClient, extract_content, collect_filing_contents,
                             enrich_research_audit, valid_document_url, write_content_report)
from sec_filings import SecClient, SourceUnavailable

CIK = "0000001234"
ACCESSION = "0000001234-26-000001"
BASE = "https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/"
DOC = {"url": BASE + "report.htm", "accessionNumber": ACCESSION, "form": "10-Q", "filingDate": "2026-10-21"}
BODY = """<html><head><title>Test filing</title><script>bankruptcy $999 billion</script></head><body>
<div style='display: none'>going concern $888 billion</div><ix:hidden>default $777 billion</ix:hidden>
<p>Fictional test disclosure. A $600 million delayed draw facility is available until December 23, 2026, subject to conditions. It matures three years after funding and proceeds are intended to repay existing notes.</p>
<p>Debt covenants include an interest coverage ratio. Default provisions can refer to insolvency without stating that a default has occurred. No automatic conclusion should be drawn.</p>
<p>Convertible notes and capped calls require a dilution review. The outlook and guidance are conditional and must not be interpreted as a recovery promise.</p>
<table><tr><td>Debt maturity year</td><td>2027</td></tr><tr><td>Principal amount</td><td>$420 million</td></tr></table>
<a href='ex10.htm'>Exhibit 10.1</a><a href='https://other.example/ex99.htm'>Exhibit 99.1 external</a>
</body></html>"""


def check():
    return {"cik": CIK, "latest_financial_report": dict(DOC), "event_filings": []}


def test_content_index_keeps_raw_facts_and_never_interprets_boilerplate_as_distress():
    result = extract_content(BODY, DOC, CIK)
    assert result["status"] == "INDEXED_FOR_REVIEW"
    assert result["topics"]["debt_maturities"]["matched_blocks"] > 0
    tokens = [value for topic in result["topics"].values() for location in topic["locations"] for value in location["raw_amount_date_tokens"]]
    assert "$600 million" in tokens and "December 23, 2026" in tokens
    assert not any(value in str(result) for value in ("999 billion", "888 billion", "777 billion"))
    assert result["exhibit_links"][0]["url"] == BASE + "ex10.htm"
    assert len(result["exhibit_links"]) == 1
    assert "clear" in result["notice"] and "no risk" in result["notice"]
    assert "EXCLUDE" not in result and "PASS" not in result


def test_real_sec_xml_encoding_declarations_are_supported():
    body = '<?xml version="1.0" encoding="UTF-8"?>' + BODY
    result = extract_content(body, DOC, CIK)
    assert result["status"] == "INDEXED_FOR_REVIEW"
    assert result["topics"]["debt_maturities"]["matched_blocks"] > 0


def test_real_filing_comments_and_empty_style_attributes_do_not_crash_indexing():
    body = BODY.replace("<body>", "<body><!-- SEC document comment --><?filing instruction?>")
    body = body.replace("<p>", "<p style>", 1)
    result = extract_content(body, DOC, CIK)
    assert result["status"] == "INDEXED_FOR_REVIEW"
    assert result["topics"]["covenants"]["matched_blocks"] > 0


@pytest.mark.parametrize("url", ["http://www.sec.gov/Archives/edgar/data/1234/000000123426000001/report.htm",
    BASE + "../other.htm", BASE + "%2e%2e%2fother.htm", BASE + "report.htm?redirect=elsewhere",
    BASE + "report.pdf", "https://www.sec.gov.evil.example/report.htm", "https://user:password@www.sec.gov/report.htm",
    "https://www.sec.gov/Archives/edgar/data/9999/000000123426000001/report.htm"])
def test_only_same_issuer_accession_html_documents_can_be_downloaded(url):
    assert not valid_document_url(url, CIK, ACCESSION)


def test_access_errors_are_retained_and_do_not_become_empty_success(tmp_path):
    client = SimpleNamespace(get=Mock(side_effect=SourceUnavailable("Filing document HTTP 403")))
    result = collect_filing_contents(check(), client)
    assert result["status"] == "UNVERIFIED"
    assert result["documents"][0]["reason"] == "Filing document HTTP 403"
    write_content_report([{"ticker": "TEST", "filing_content_review": result}], tmp_path / "index.md")
    assert "403" in (tmp_path / "index.md").read_text(encoding="utf-8")


def test_non_us_content_is_not_misreported_as_sec_access_failure():
    result = collect_filing_contents({"status": "NOT_COVERED"})
    assert result["status"] == "NOT_COVERED" and result["documents"] == []


def test_budget_is_visible_and_does_not_fetch_all_exhibit_or_archive_links():
    data = check()
    data["event_filings"] = [dict(DOC, url=BASE + "event.htm", form="8-K")]
    client = SimpleNamespace(get=Mock(return_value=(BODY, "2026-10-22T12:00:00Z")))
    result = collect_filing_contents(data, client, max_primary=1, max_exhibits=0)
    assert result["status"] == "PARTIAL" and result["deferred_documents"] == 2
    assert client.get.call_count == 1
    # Even a complete content index never changes the upstream solvency/event statuses.
    assert data == check() | {"event_filings": [dict(DOC, url=BASE + "event.htm", form="8-K")]}


def test_same_accession_exhibit_is_indexed_within_a_separate_budget():
    client = SimpleNamespace(get=Mock(return_value=(BODY, "2026-10-22T12:00:00Z")))
    result = collect_filing_contents(check(), client, max_primary=1, max_exhibits=1)
    assert client.get.call_count == 2
    assert len(result["documents"]) == 2 and result["documents"][1]["form"] == "EXHIBIT"


def test_empty_or_placeholder_content_is_not_success():
    for body in ("", "<html>Unavailable</html>", None):
        with pytest.raises(SourceUnavailable):
            extract_content(body, DOC, CIK)


def test_streaming_size_limit_prevents_unbounded_document_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr("filing_contents.time.sleep", lambda _: None)
    monkeypatch.setattr("filing_contents.MAX_BYTES", 20)
    response = SimpleNamespace(status_code=200, iter_content=lambda _: iter([b"x" * 15, b"x" * 15]), close=Mock())
    sec = SecClient(tmp_path, SimpleNamespace(get=Mock(return_value=response)))
    with pytest.raises(SourceUnavailable, match="limit"):
        DocumentClient(sec).get(DOC, CIK)
    response.close.assert_called_once()


def test_enrichment_preserves_selection_and_manual_holds_and_exposes_deferred_issuers(monkeypatch):
    metadata = check()
    monkeypatch.setattr("filing_contents.check_sec_filings", lambda *args, **kwargs: metadata)
    monkeypatch.setattr("filing_contents.collect_filing_contents", lambda *args, **kwargs: {"status": "INDEXED_FOR_REVIEW", "documents": []})
    audit = [{"ticker": "HOLD", "decision": "event_review", "reason": "Pending merger"},
             {"ticker": "WATCH", "decision": "selected"}]
    selected = [{"ticker": "WATCH", "goal_fit": {"status": "RESEARCH_WATCH"}}]
    original = deepcopy(audit)
    enrich_research_audit(audit, selected, max_issuers=1)
    assert [item["decision"] for item in audit] == [item["decision"] for item in original]
    assert audit[0]["filing_content_review"]["status"] == "DEFERRED_BUDGET"
    assert selected[0]["goal_fit"]["status"] == "RESEARCH_WATCH"
    assert selected[0]["filing_content_review"]["status"] == "INDEXED_FOR_REVIEW"


def test_budget_prioritizes_upside_near_misses_and_sourced_holds_without_admitting_them(monkeypatch):
    fetched = []
    def metadata(ticker, *args, **kwargs):
        fetched.append(ticker)
        return check()
    monkeypatch.setattr("filing_contents.check_sec_filings", metadata)
    monkeypatch.setattr("filing_contents.collect_filing_contents", lambda *args, **kwargs:
                        {"status": "INDEXED_FOR_REVIEW", "documents": []})
    audit = [{"ticker": "ORDINARY", "decision": "filing_review"},
             {"ticker": "HOLD", "decision": "event_review", "review_hold": {"status": "PENDING"}},
             {"ticker": "NEAR", "decision": "risk_excluded", "solvency": {"status": "REVIEW"},
              "valuation": {"plausible_upside_screen": True}},
             {"ticker": "SELECTED", "decision": "selected"}]
    original = deepcopy(audit)
    selected = [{"ticker": "SELECTED"}]
    enrich_research_audit(audit, selected, max_issuers=3)
    assert fetched == ["SELECTED", "NEAR", "HOLD"]
    assert audit[0]["filing_content_review"]["status"] == "DEFERRED_BUDGET"
    assert [item["decision"] for item in audit] == [item["decision"] for item in original]
    assert audit[1]["review_hold"] == original[1]["review_hold"]
    assert selected == [{"ticker": "SELECTED", "filing_content_review":
                         {"status": "INDEXED_FOR_REVIEW", "documents": []}}]


def test_upside_does_not_expand_collection_to_hard_failures_or_unknown_financials(monkeypatch):
    collect = Mock()
    monkeypatch.setattr("filing_contents.collect_filing_contents", collect)
    audit = [{"ticker": status, "decision": "risk_excluded", "solvency": {"status": status},
              "valuation": {"plausible_upside_screen": True}}
             for status in ("EXCLUDE", "UNVERIFIED", "SPECIALIST_REVIEW")]
    audit += [{"ticker": "NO_UPSIDE", "decision": "risk_excluded", "solvency": {"status": "REVIEW"},
               "valuation": {"plausible_upside_screen": False}}]
    original = deepcopy(audit)
    enrich_research_audit(audit, [], max_issuers=3)
    assert audit == original
    collect.assert_not_called()


def test_routine_filing_queue_rotates_full_batches_without_starving_held_issuers(monkeypatch):
    from datetime import date, timedelta
    fetched = []
    def metadata(ticker, *args, **kwargs):
        fetched.append(ticker)
        return check()
    monkeypatch.setattr("filing_contents.check_sec_filings", metadata)
    monkeypatch.setattr("filing_contents.collect_filing_contents", lambda *args, **kwargs:
                        {"status": "INDEXED_FOR_REVIEW", "documents": []})
    routine = [{"ticker": f"R{i}", "decision": "filing_review"} for i in range(8)]
    seen = []
    for index in range(4):
        audit = deepcopy(routine) + [{"ticker": "HOLD", "decision": "event_review",
                                     "review_hold": {"status": "PENDING"}}]
        fetched.clear()
        enrich_research_audit(audit, [], max_issuers=3,
                              rotation_day=date(2026, 10, 22) + timedelta(days=index))
        assert fetched[0] == "HOLD" and len(fetched) == 3
        seen.extend(fetched[1:])
        assert sum(x["filing_content_review"]["status"] == "DEFERRED_BUDGET" for x in audit) == 6
        assert all(x["decision"] == "filing_review" for x in audit[:-1])
    assert sorted(seen) == [f"R{i}" for i in range(8)]


def test_routine_rotation_is_stable_within_a_day_and_independent_of_input_order(monkeypatch):
    from datetime import date
    fetched = []
    def metadata(ticker, *args, **kwargs):
        fetched.append(ticker)
        return check()
    monkeypatch.setattr("filing_contents.check_sec_filings", metadata)
    monkeypatch.setattr("filing_contents.collect_filing_contents", lambda *args, **kwargs:
                        {"status": "INDEXED_FOR_REVIEW", "documents": []})
    routine = [{"ticker": f"R{i}", "decision": "filing_review"} for i in range(7)]
    enrich_research_audit(deepcopy(routine), [], max_issuers=3, rotation_day=date(2026, 10, 22))
    first = list(fetched)
    fetched.clear()
    enrich_research_audit(list(reversed(deepcopy(routine))), [], max_issuers=3,
                          rotation_day=date(2026, 10, 22))
    assert fetched == first
