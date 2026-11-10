from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

import ai_research as ai

NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
URLS = ["https://www.sec.gov/Archives/report.htm", "https://www.sec.gov/Archives/annual.htm"]


def brief(ticker="ABC"):
    result = {key: "Sourced finding with material uncertainty" for key, spec in ai.SCHEMA["properties"].items() if spec["type"] == "string"}
    result.update(ticker=ticker, verdict="FOLLOW_UP", risks=["Customer spending could decline"],
                  unresolved=["Covenant stress remains unresolved"], next_review_by="2026-12-01",
                  target_by="2027-11-01", valuation_available=True,
                  sources=[{"id": str(i), "url": url, "published_at": "2026-11-01", "finding": "Filing evidence"}
                           for i, url in enumerate(URLS)])
    for name, cash in (("bear", 5), ("base", 10), ("recovery", 20)):
        result[name] = {"annual_equity_cash_usd": cash, "multiple": 20,
                        "dilution_pct": 5, "rationale": "Conditional assumptions", "source_ids": ["0"]}
    return result


def inputs(tickers=("ABC",)):
    candidates = [{"ticker": t, "market_cap_usd": 150, "current_price": 10} for t in tickers]
    audit = [{"ticker": t, "company": t, "decision": "filing_review", "reason": "Financing review required",
              "solvency": {"status": "REVIEW"}, "observed_price": 10, "quote_currency": "USD",
              "quote_observed_at": NOW.isoformat(), "official_filing_check": {
                  "latest_financial_report": {"url": URLS[0]}, "latest_annual_report": {"url": URLS[1]}}}
             for t in tickers]
    return candidates, audit


def responses(ticker="ABC"):
    research = {"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 100}, "output": [
        {"type": "reasoning", "content": None},
        {"type": "web_search_call", "status": "completed", "action": {"type": "search", "sources": [{"url": url} for url in URLS]}},
        {"type": "message", "content": [{"type": "output_text", "text": "Primary research", "annotations": []}]}]}
    extraction = {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(brief(ticker))}]}]}
    return research, extraction


def context():
    return ai.contexts(*inputs(), None, None, NOW)[0]


def test_missing_key_is_visible_and_never_calls_api(tmp_path):
    result = ai.run_research(*inputs(), None, None, tmp_path, now=NOW, key="",
                             transport=lambda _: pytest.fail("No API without a key"))
    assert result["status"] == "DISABLED_NO_KEY"
    assert not (tmp_path/"ai_research_state.json").exists()
    assert "DISABLED_NO_KEY" in (tmp_path/"ai_research.md").read_text()


def test_request_contract_sources_cache_and_no_automatic_admission(tmp_path):
    payloads = []
    def transport(payload):
        payloads.append(payload)
        return responses()[len(payloads)-1]
    before = deepcopy(inputs())
    result = ai.run_research(*before, None, None, tmp_path, now=NOW, key="test", transport=transport)
    assert result["status"] == "COMPLETED" and len(result["shortlist"]) == 1
    assert len(payloads) == 2
    assert payloads[0]["tool_choice"] == "required" and payloads[0]["max_tool_calls"] == 4
    assert payloads[1]["text"]["format"]["strict"]
    assert all(not p["store"] and p["max_output_tokens"] == 5000 for p in payloads)
    assert not list(tmp_path.glob("recovery_cases*")) and not list(tmp_path.glob("paper*"))
    assert before == inputs()
    again = ai.run_research(*before, None, None, tmp_path, now=NOW, key="test",
                            transport=lambda _: pytest.fail("Fresh cached research should be reused"))
    assert again["shortlist"][0]["reused"] and again["requests_today"] == 2


def test_daily_budget_survives_reruns_and_failed_calls(tmp_path):
    tickers = tuple(f"CO{i}" for i in range(10))
    calls = []
    def fail(payload):
        calls.append(payload)
        raise RuntimeError("Bearer secret-token must never be logged")
    result = ai.run_research(*inputs(tickers), None, None, tmp_path, now=NOW, key="secret-token", transport=fail)
    assert len(calls) == 3 and result["requests_today"] == 3
    assert len(result["companies_attempted_today"]) == 3
    again = ai.run_research(*inputs(tickers), None, None, tmp_path, now=NOW, key="test", transport=fail)
    assert len(calls) == 3
    assert "secret-token" not in (tmp_path/"ai_research.json").read_text()
    state = json.loads((tmp_path/"ai_research_state.json").read_text())
    assert state["days"]["2026-11-10"]["requests"] == 3
    assert not again["shortlist"]


def test_corrupt_state_cannot_reset_spending(tmp_path):
    (tmp_path/"ai_research_state.json").write_text("broken")
    result = ai.run_research(*inputs(), None, None, tmp_path, now=NOW, key="test",
                             transport=lambda _: pytest.fail("Corrupt budget state must fail closed"))
    assert result["status"] == "STATE_INVALID_NO_SPEND"


@pytest.mark.parametrize("change", [
    lambda b: b.update(ticker="WRONG"),
    lambda b: b["sources"][0].update(url="https://www.sec.gov/invented"),
    lambda b: b["sources"][0].update(url="https://attacker.example/report"),
    lambda b: b["sources"][0].update(published_at="2027-01-01"),
    lambda b: b["sources"].pop(),
    lambda b: b["sources"][1].update(url=URLS[0]),
    lambda b: b.update(next_review_by="2027-03-01"),
    lambda b: b.update(target_by="2029-01-01"),
    lambda b: b["recovery"].update(annual_equity_cash_usd=float("nan")),
    lambda b: b["recovery"].update(annual_equity_cash_usd="20"),
    lambda b: b["recovery"].update(source_ids=["invented"]),
    lambda b: b["recovery"].update(annual_equity_cash_usd=1),
    lambda b: b.update(verdict="PROMISING"),
    lambda b: b.update(risks=[]),
])
def test_invalid_issuer_sources_assumptions_and_checkpoints_fail_closed(change):
    b = brief()
    change(b)
    with pytest.raises((ValueError, TypeError)):
        ai.validate_brief(b, context(), set(URLS) | {"https://attacker.example/report"}, NOW)


def test_refusal_and_no_search_cannot_become_research():
    with pytest.raises(ai.APIError):
        ai.response_text({"output": [{"content": [{"type": "refusal"}]}]})
    with pytest.raises(ai.APIError):
        ai.retrieved_urls({"output": [{"content": [{"type": "output_text", "text": "Made-up sources"}]}]})


def test_fresh_documents_invalidate_cache_and_old_briefs_are_not_shown(tmp_path):
    values = iter(responses())
    ai.run_research(*inputs(), None, None, tmp_path, now=NOW, key="test", transport=lambda _: next(values))
    candidates, audit = inputs()
    audit[0]["official_filing_check"]["latest_financial_report"]["url"] += "?amendment=1"
    result = ai.run_research(candidates, audit, None, None, tmp_path, now=NOW, key="test",
                             transport=lambda _: pytest.fail("Same company cannot be charged again today"))
    assert not result["shortlist"]


def test_hard_exclusions_not_researched_even_when_shadow_observed():
    candidates, audit = inputs()
    audit[0]["solvency"]["status"] = "EXCLUDE"
    assert ai.contexts(candidates, audit, None, {"observations": [{"ticker": "ABC"}]}, NOW) == []
    audit[0]["solvency"]["status"] = "REVIEW"
    audit[0]["decision"] = "risk_excluded"
    assert ai.contexts(candidates, audit, None, None, NOW) == []


def test_changed_disclosures_prioritized_and_not_claimed_as_price_candidates():
    watches = {"watches": [{"ticker": "TTD", "actionable_change": True, "question": "Review", "documents": []}]}
    result = ai.contexts(*inputs(), watches, None, NOW)
    assert result[0]["ticker"] == "TTD" and not result[0]["in_current_price_candidates"]


def test_valuation_recomputed_from_current_cap_with_dilution_and_horizon():
    c, b = context(), brief()
    expected = (400 / 1.05 / 150 - 1)*100
    result = ai.valuation(b, c, NOW)
    assert result["recovery"]["upside_pct"] == pytest.approx(expected)
    assert result["required_recovery_upside_pct"] == 50
    b["target_by"] = "2028-01-01"
    assert ai.valuation(b, c, NOW)["required_recovery_upside_pct"] == 100
    c["market_cap_usd"] *= 2
    assert ai.valuation(b, c, NOW)["recovery"]["upside_pct"] < expected
    c["quote_observed_at"] = "2026-10-01T12:00:00Z"
    assert ai.valuation(b, c, NOW) is None


def test_combined_email_cap_dedup_escape_and_subject_agree():
    b = brief()
    b["thesis"] = '<script>alert("bad")</script>'
    row = {"ticker": "ABC", "brief": b, "reviewed_at": NOW.isoformat(), "reused": False,
           "in_current_price_candidates": True, "core_decision": "filing_review", "core_reason": "Review required", "valuation": None}
    report = {"status": "COMPLETED", "shortlist": [{**deepcopy(row), "ticker": f"CO{i}"} for i in range(15)]}
    stocks = [{"ticker": "CO0"}, {"ticker": "QUAL", "goal_fit": {"status": "DOCUMENTED_24M_CASE"}}]
    output = ai.compact_email_html(report, stocks, {})
    assert output.count("<h3>") == 10
    assert output.count("CO0 —") == 1
    assert "<script>" not in output and "&lt;script&gt;" in output
    assert "10 companies to review (1 documented cases, 8 AI leads)" in ai.email_subject(report, stocks)


def test_http_errors_are_sanitized_and_redirects_disabled(monkeypatch):
    class Response:
        status_code = 401
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def post(url, **kwargs):
        assert url == "https://api.openai.com/v1/responses"
        assert kwargs["allow_redirects"] is False
        return Response()
    monkeypatch.setattr(ai.requests, "post", post)
    with pytest.raises(ai.APIError, match="^HTTP_401$"):
        ai.post_response({}, "a-secret")


def test_compact_mode_omits_the_large_backlog(monkeypatch):
    import scanner_entry
    monkeypatch.setattr(scanner_entry.scanner, "AI_RESEARCH_ENABLED", True, raising=False)
    monkeypatch.setattr(scanner_entry.scanner, "_last_ai_research", {"status": "DISABLED_NO_KEY", "shortlist": []}, raising=False)
    monkeypatch.setattr(scanner_entry.scanner, "REPORT_SCOPE", {}, raising=False)
    output = scanner_entry.generate_email_html_consistent([], [{"ticker": "NOT_A_PICK"}], [])
    assert "DISABLED_NO_KEY" in output and "NOT_A_PICK" not in output


def test_saved_report_probe_never_spends_on_stale_input(tmp_path):
    (tmp_path/"research_report.json").write_text(json.dumps({"generated_at": "2026-10-01T12:00:00Z"}))
    report = ai.run_saved_report(tmp_path, now=NOW, key="test",
        transport=lambda _: pytest.fail("Stale input must not trigger paid research"))
    assert report["status"] == "STALE_INPUT_NO_SPEND"


def test_saved_report_probe_uses_same_run_cap_and_writes_preview_only(tmp_path):
    candidates, audit = inputs()
    (tmp_path/"research_report.json").write_text(json.dumps({"generated_at": NOW.isoformat(),
        "candidates": audit, "selected_tickers": [], "scan_scope": {}}))
    (tmp_path/"growth_recovery_shadow.json").write_text(json.dumps({"generated_at": NOW.isoformat(),
        "records": [{"ticker": "ABC", "observed_price": 10, "market_cap_usd": 150}]}))
    values = iter(responses())
    report = ai.run_saved_report(tmp_path, now=NOW, key="test", transport=lambda _: next(values))
    assert report["status"] == "COMPLETED" and report["shortlist"][0]["valuation"]
    assert "ABC" in (tmp_path/"ai_email_preview.html").read_text()
    assert not list(tmp_path.glob("paper*")) and not list(tmp_path.glob("scanner_memory*"))


def test_main_integrates_pilot_without_turning_briefs_into_selections(monkeypatch, tmp_path):
    from unittest.mock import Mock
    import scanner_entry
    scanner = scanner_entry.scanner
    monkeypatch.setattr(scanner, "AI_RESEARCH_ENABLED", True, raising=False)
    monkeypatch.setattr(scanner, "_last_disclosure_watch", None, raising=False)
    monkeypatch.setattr(scanner, "REPORT_SCOPE", {"type": "fixture"}, raising=False)
    monkeypatch.setattr(scanner, "REPORT_PREFIX", str(tmp_path/"research_report"), raising=False)
    monkeypatch.setattr(scanner, "load_memory", lambda: {})
    monkeypatch.setattr(scanner, "check_price_alerts", lambda _: [])
    monkeypatch.setattr(scanner, "stage1_quick_filter", lambda: ([], []))
    monkeypatch.setattr(scanner, "enrich_research_audit", Mock())
    send = Mock(return_value=False)
    monkeypatch.setattr(scanner, "send_email", send)
    hook = Mock(return_value={"status": "DISABLED_NO_KEY", "shortlist": []})
    monkeypatch.setattr(ai, "run_research", hook)
    scanner.main()
    hook.assert_called_once()
    send.assert_called_once()
    assert "0 companies to review" in send.call_args.args[0]
    saved = json.loads((tmp_path/"research_report.json").read_text())
    assert saved["selected_tickers"] == [] and saved["scan_scope"]["ai_research"]["status"] == "DISABLED_NO_KEY"
    assert not (tmp_path/"paper_tracking.json").exists()


def test_incomplete_output_records_usage_and_explicit_repair_cannot_exceed_allowance(tmp_path):
    incomplete = {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
                  "usage": {"input_tokens": 200, "output_tokens": 5000}, "output": []}
    report = ai.run_research(*inputs(), None, None, tmp_path, now=NOW, key="test", transport=lambda _: incomplete)
    assert report["failures"][0]["error"] == "INCOMPLETE_MAX_OUTPUT_TOKENS"
    state = json.loads((tmp_path/"ai_research_state.json").read_text())
    assert state["days"]["2026-11-10"]["responses"][0]["usage"]["output_tokens"] == 5000
    research, extraction = responses()
    combined = deepcopy(research)
    combined["output"][-1]["content"][0]["text"] = extraction["output"][0]["content"][0]["text"]
    payloads = []
    def transport(payload):
        payloads.append(payload)
        return combined
    result = ai.run_research(*inputs(), None, None, tmp_path, now=NOW, key="test",
                             transport=transport, resume_incomplete=True)
    assert result["requests_today"] == 2 and len(payloads) == 1
    assert payloads[0]["text"]["format"]["strict"] and payloads[0]["tools"]
    assert result["shortlist"]
    ai.run_research(*inputs(), None, None, tmp_path, now=NOW, key="test", resume_incomplete=True,
                    transport=lambda _: pytest.fail("No repeated repair or extra requests"))


def test_global_auth_failure_stops_other_company_requests(tmp_path):
    calls = []
    def transport(payload):
        calls.append(payload)
        raise ai.APIError("HTTP_401")
    result = ai.run_research(*inputs(("ONE", "TWO", "THREE")), None, None, tmp_path,
                             now=NOW, key="test", transport=transport)
    assert len(calls) == 1 and result["requests_today"] == 1


def test_development_authorization_expires_without_spending(tmp_path):
    with pytest.raises(ValueError, match="authorization expired"):
        ai.development_probe(tmp_path, "ABC", "2026-11-09", now=NOW, key="test",
                             transport=lambda _: pytest.fail("Expired development authorization"))
    assert not (tmp_path/"ai_research_state.json").exists()


def test_hidden_core_selections_are_not_marked_as_emailed(monkeypatch, tmp_path):
    from unittest.mock import Mock
    import scanner_entry
    scanner = scanner_entry.scanner
    monkeypatch.setattr(scanner, "AI_RESEARCH_ENABLED", True, raising=False)
    monkeypatch.setattr(scanner, "PAPER_TRACKING_ENABLED", False, raising=False)
    monkeypatch.setattr(scanner, "_last_disclosure_watch", None, raising=False)
    monkeypatch.setattr(scanner, "REPORT_SCOPE", {}, raising=False)
    monkeypatch.setattr(scanner, "REPORT_PREFIX", str(tmp_path/"research_report"), raising=False)
    memory = {"sent_stocks": {}, "tracked_prices": {}}
    monkeypatch.setattr(scanner, "load_memory", lambda: memory)
    monkeypatch.setattr(scanner, "save_memory", Mock())
    monkeypatch.setattr(scanner, "check_price_alerts", lambda _: [])
    monkeypatch.setattr(scanner, "stage1_quick_filter", lambda: ([{"ticker": "ABC"}], []))
    stocks = [{"ticker": f"CO{i}", "current_price": 10, "currency": "USD"} for i in range(15)]
    monkeypatch.setattr(scanner, "stage2_deep_analysis", lambda *a: (stocks, []))
    monkeypatch.setattr(scanner, "enrich_research_audit", Mock())
    monkeypatch.setattr(scanner, "send_email", Mock(return_value=True))
    monkeypatch.setattr(ai, "run_research", Mock(return_value={"status": "COMPLETED", "shortlist": []}))
    scanner.main()
    assert len(memory["sent_stocks"]) == 10 and len(memory["tracked_prices"]) == 10
