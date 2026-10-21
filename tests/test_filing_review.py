from copy import deepcopy

import pytest

from filing_review import filing_review_plan, filing_links_html, safe_website, write_filing_queue


@pytest.mark.parametrize("ticker,label", [("AAA", "SEC EDGAR"), ("AAA.L", "FCA"),
    ("AAA.TA", "TASE MAYA"), ("AAA.WA", "KNF"), ("AAA.DE", "German Company Register")])
def test_public_routes_follow_listing_market_without_claiming_verified_facts(ticker, label):
    plan = filing_review_plan(ticker, "Example Parent")
    assert any(label in source["label"] for source in plan["source_links"])
    assert plan["status"] == "PENDING_DOCUMENT_REVIEW"
    assert "No screening status is upgraded" in plan["notice"]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,bad", "https://user:password@example.com", "not-a-url"])
def test_non_web_urls_and_embedded_credentials_are_not_linked(url):
    assert safe_website(url) is None
    plan = filing_review_plan("AAA", website=url)
    assert not any(source["role"].startswith("quote-provider") for source in plan["source_links"])


def test_issuer_link_is_preserved_but_external_text_is_escaped():
    plan = filing_review_plan("AAA", "<script>issuer</script>", "https://example.com/investors")
    html = filing_links_html(plan)
    assert '<script>' not in html
    assert 'https://example.com/investors' in html
    assert 'Review remains pending' in html


def test_queue_retains_missing_questions_without_promoting_or_researching_excluded_names(tmp_path):
    audit = [{"ticker": "AAA", "decision": "unverified", "solvency": {"status": "UNVERIFIED", "missing": ["Gross interest evidence"]}},
             {"ticker": "BBB", "decision": "exclude", "reason": "Liquidity gap"}]
    original = deepcopy(audit)
    path = tmp_path / "filings.md"
    write_filing_queue(audit, path)
    text = path.read_text(encoding="utf-8")
    assert 'Gross interest evidence' in text
    assert '## AAA' in text
    assert '## BBB' not in text
    assert audit == original


def test_empty_queue_does_not_invent_stocks_to_research(tmp_path):
    path = tmp_path / "filings.md"
    write_filing_queue([], path)
    assert 'No candidates currently require' in path.read_text(encoding="utf-8")
