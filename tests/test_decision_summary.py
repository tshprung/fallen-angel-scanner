import json

from research_reporting import (decision_summary, decision_summary_html,
                                filing_review_summary_html, write_research_report)


def test_each_final_outcome_is_counted_once_including_unknown_and_source_errors():
    decisions = ["selected", "exclude", "risk_excluded", "not_selected", "final_filter_excluded",
                 "specialist_review", "unverified", "event_review", "filing_review", "filing_unverified",
                 "insufficient_value_upside", "valuation_unverified", "analysis_error", "new_future_status"]
    result = decision_summary([{"decision": value} for value in decisions])
    assert sum(result["outcomes"].values()) == result["audited_candidates"] == 14
    assert result["outcomes"]["Financial/risk exclusions"] == 2
    assert result["outcomes"]["Filing/event review unresolved"] == 3
    assert result["outcomes"]["Price-pattern/timing/other exclusions"] == 3
    assert result["outcomes"]["Analysis errors"] == 1


def test_zero_selections_and_partial_scan_do_not_imply_full_market_coverage():
    audit = [{"decision": "filing_review", "filing_content_review": {"status": "DEFERRED_BUDGET"}},
             {"decision": "filing_unverified"}]
    scope = {"stage1_coverage": {"processed_count": 10, "requested_count": 100, "completed": False,
                               "data_gaps": [{}]},
             "provider_health": {"status": "DEGRADED <source>", "company_analysis_errors": 0,
                                 "company_candidates": 2}}
    output = decision_summary_html(audit, scope)
    assert "10/100" in output and "completed: False" in output
    assert "DEFERRED_BUDGET: 1" in output and "NOT_COLLECTED: 1" in output
    assert "not a demonstrated financial failure" in output
    assert "resolving it alone does not qualify" in output
    assert "&lt;source&gt;" in output and "<source>" not in output
    assert "older saved baselines" in output


def test_empty_audit_is_an_explicit_zero_without_invented_coverage():
    output = decision_summary_html([])
    assert "0 price-screen candidates" in output and "Processed" not in output
    assert all(value == 0 for value in decision_summary([])["outcomes"].values())


def test_concise_held_email_preserves_full_reason_and_source_queue(tmp_path):
    docs = [{"url": f"https://www.sec.gov/Archives/edgar/data/1/file-{i}.htm",
             "form": "8-K", "filingDate": "2026-10-28", "accessionNumber": f"fixture-{i}"} for i in range(20)]
    reason = ("Source event requires reconciliation. " * 80) + "Unique final evidence question"
    item = {"ticker": "AAA", "decision": "filing_review", "reason": reason,
            "official_filing_check": {"status": "REVIEW_REQUIRED", "event_filings": docs,
                                      "checked_at": "2026-10-28T23:00:00Z", "notice": "Metadata only"}}
    output = filing_review_summary_html([item])
    assert len(output) < 1600 and "18 more source links" in output
    assert docs[0]["url"] in output and docs[-1]["url"] not in output
    assert "full reason in filing_review.md" in output
    write_research_report([item], [], tmp_path / "report")
    saved = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert saved["candidates"][0]["reason"] == reason
    assert docs[-1]["url"] in (tmp_path / "filing_review.md").read_text(encoding="utf-8")
    assert reason in (tmp_path / "filing_review.md").read_text(encoding="utf-8")
    assert saved["decision_summary"] == decision_summary([item])


def test_held_email_rejects_script_links_and_preserves_manual_findings():
    item = {"ticker": "<AAA>", "decision": "event_review", "reason": "<script>unsafe</script>",
            "review_hold": {"sources": [{"url": "javascript:alert(1)", "published_at": "2026-10-27"}],
                "review_notes": [{"finding": "Funding drawn; hold remains pending <review>",
                                  "source_url": "https://issuer.example/report"}]}}
    output = filing_review_summary_html([item])
    assert "<script>" not in output and "javascript:" not in output
    assert "Funding drawn; hold remains pending &lt;review&gt;" in output


def test_real_email_inserts_summary_and_held_details_inside_body(monkeypatch):
    import scanner_entry
    item = {"ticker": "AAA", "decision": "filing_review", "reason": "Reconcile results"}
    monkeypatch.setattr(scanner_entry.scanner, "_last_research_audit", [item], raising=False)
    monkeypatch.setattr(scanner_entry.scanner, "REPORT_SCOPE", {}, raising=False)
    monkeypatch.setattr(scanner_entry.scanner, "_last_disclosure_watch", None, raising=False)
    output = scanner_entry.generate_email_html_consistent([], [], [])
    assert output.index("What happened in this scan") < output.index("Held for filing review")
    assert output.index("Held for filing review") < output.index("</body>")
