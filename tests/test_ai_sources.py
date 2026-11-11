from copy import deepcopy
from unittest.mock import Mock

import pytest

import ai_sources as sources
import ai_research as ai
from sec_filings import SourceUnavailable

BASE = "https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/"
BODY = "<html><body><p>" + "Disclosed cash and liquidity are subject to lender conditions. " * 6 + "</p></body></html>"


def test_packet_only_contains_successfully_read_same_issuer_sources():
    urls = [BASE + "report.htm", BASE + "missing.htm"]
    client = Mock()
    client.get.side_effect = [(BODY, "2026-11-11T00:00:00+00:00"), SourceUnavailable("not available")]
    result = sources.primary_packet({"source_urls": urls}, {
        "https://evil.example/filing.htm", BASE + "../secret.htm",
        BASE.replace("/1234/", "/9999/") + "other.htm", BASE + "report.pdf"}, client)
    assert client.get.call_count == 2
    assert [row["url"] for row in result["documents"]] == urls[:1]
    assert result["documents"][0]["text_blocks"][0]["text"].startswith("Disclosed cash")
    assert result["failures"] == [{"url": urls[1], "error": "PRIMARY_CONTENT_UNAVAILABLE"}]


def test_source_packet_and_exhibit_reads_share_six_document_limit():
    client = Mock()
    client.get.return_value = (BODY + "<a href='ex99.htm'>Exhibit 99.1</a>", "2026-11-11T00:00:00+00:00")
    result = sources.primary_packet({"source_urls": [BASE + f"report{i}.htm" for i in range(10)]}, set(), client)
    assert client.get.call_count == sources.MAX_DOCUMENTS == len(result["documents"])
    assert result["documents"][1]["url"] == BASE + "ex99.htm"


def test_raw_excerpts_strip_hidden_instructions_and_expose_truncation():
    from filing_contents import extract_content
    doc = {"url": BASE + "report.htm", "accessionNumber": "0000001234-26-000001", "form": "10-Q"}
    body = "<html><body><script>secret instructions</script><p hidden>hidden instructions</p><p>" + "cash flow " * 10000 + "</p></body></html>"
    parsed = extract_content(body, doc, "1234", include_text=True)
    assert sum(len(row["text"]) for row in parsed["text_blocks"]) <= 14000
    assert parsed["text_is_partial"] and parsed["text_blocks"][0]["truncated"]
    assert "instructions" not in str(parsed["text_blocks"])


def test_reviewer_citations_are_constrained_to_provided_raw_sources(monkeypatch):
    from tests.test_ai_research import responses, context, NOW, URLS
    packet = {"documents": [{"url": url, "text_blocks": [{"text": "Actual source evidence"}]} for url in URLS], "failures": []}
    monkeypatch.setattr(sources, "primary_packet", lambda *_: packet)
    first, second = responses()
    # No second web call is needed when two actual primary documents are supplied.
    second["output"] = second["output"][:1]
    payloads = []
    replies = iter([first, second])
    def request(payload):
        payloads.append(deepcopy(payload))
        return next(replies)
    result = ai.research_one(context(), NOW, request)
    spec = payloads[1]["text"]["format"]["schema"]["properties"]["sources"]["items"]["properties"]["url"]
    assert spec["enum"] == sorted(URLS)
    assert "Actual source evidence" in payloads[1]["input"]
    assert set(result["retrieved_urls"]) == set(URLS)
    second["output"][0]["content"][0]["text"] = second["output"][0]["content"][0]["text"].replace(URLS[0], BASE + "unread.htm")
    replies = iter([first, second])
    with pytest.raises(ai.ResearchError, match="SOURCE_NOT_RETRIEVED"):
        ai.research_one(context(), NOW, request)
