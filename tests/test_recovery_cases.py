import numpy as np
import pandas as pd
import pytest

from fundamental_analysis import load_policy
from recovery_cases import RISK_TOPICS, assess_recovery_case
from research_reporting import candidate_needs_review, financial_detail_html, write_research_report
from screening import drawdown_candidate

NOW = "2026-10-22T12:00:00Z"


def source_block(**extra):
    return {"finding": "Fictional test finding; not an issuer claim or investment recommendation",
            "sources": [{"url": "https://example.com/fixture-disclosure", "published_at": "2026-10-21"}], **extra}


def stock():
    return {"ticker": "TEST", "currency": "USD", "current_price": 10, "market_cap_usd": 1e9,
            "price_dislocation": {"drop_recent_peak_pct": -35, "recent_peak_age_sessions": 30, "recent_peak_date": "2026-09-10"},
            "solvency": {"status": "REVIEW"},
            "official_filing_check": {"status": "METADATA_CHECKED", "blocks_selection": False,
                "checked_at": NOW, "notice": "Fixture SEC metadata; contents not verified", "findings": [],
                "latest_financial_report": {"accessionNumber": "0000001234-26-000001", "form": "10-Q",
                    "reportDate": "2026-09-30", "filingDate": "2026-10-21", "url": "https://example.com/fixture-disclosure"}},
            "financial_evidence": {"balance": {"asof": "2026-09-30"},
                "cashflow": {"asof": "2026-09-30", "values": {"ocf": 160e6, "fcf": 100e6}},
                "income": {"asof": "2026-09-30", "values": {"ebit": 120e6}}},
            "valuation": {"normalized_fcf_usd": 92e6, "assumed_share_dilution": .05}}


def reviewed_case():
    return {"reviewed_at": "2026-10-21", "target_by": "2027-10-01",
            "statement_periods": {name: "2026-09-30" for name in ("balance", "cashflow", "income")},
            "filing_accession": "0000001234-26-000001", "cause": source_block(),
            "catalyst": source_block(expected_by="2027-03-01", metric="Fixture: restored operating margin", invalidation="Fixture: margin recovery does not occur"),
            "risk_reviews": {topic: source_block(status="REVIEWED_NO_UNRESOLVED_CONCERN") for topic in RISK_TOPICS},
            "valuation": source_block(basis="equity_fcf_usd_after_financing", expected_dilution_fraction=.05,
                cases={"bear": source_block(equity_fcf_usd=60e6, equity_fcf_multiple=10),
                       "base": source_block(equity_fcf_usd=100e6, equity_fcf_multiple=15),
                       "recovery": source_block(equity_fcf_usd=130e6, equity_fcf_multiple=20)})}


def test_generic_bull_sensitivity_and_cheapness_do_not_establish_a_year_case():
    data = stock()
    data["valuation"].update(bull_2x=True, plausible_upside_screen=True)
    result = assess_recovery_case(data, now=NOW)
    assert result["status"] == "RESEARCH_WATCH"
    assert result["cases"] == {}
    assert any("catalyst" in message for message in result["missing"])
    requirement = result["doubling_requirements"]
    assert requirement["target_price"] == 20
    assert requirement["equity_fcf_multiple_at_unchanged_normalized_fcf"] == pytest.approx(2.1e9 / 92e6)
    assert requirement["required_equity_fcf_usd_by_multiple"]["15"] == pytest.approx(140e6)


def test_sourced_company_case_is_conditional_and_accounts_for_dilution_without_double_subtracting_debt():
    result = assess_recovery_case(stock(), reviewed_case(), now=NOW)
    assert result["status"] == "DOCUMENTED_12M_CASE"
    assert not result["missing"]
    assert result["cases"]["recovery"]["price"] == pytest.approx(10 * 2.6 / 1.05)
    assert result["cases"]["recovery"]["return_pct"] > 100
    assert "no guarantee" in result["notice"]


def test_case_review_cannot_claim_to_use_a_later_publication():
    record = reviewed_case()
    record["reviewed_at"] = "2026-10-20"
    result = assess_recovery_case(stock(), record, now=NOW)
    assert result["status"] == "RESEARCH_WATCH"


def test_quote_units_do_not_change_company_case_percentage_returns():
    dollars = assess_recovery_case(stock(), reviewed_case(), now=NOW)
    pence_stock = stock()
    pence_stock.update(current_price=1000, currency="GBp")
    pence = assess_recovery_case(pence_stock, reviewed_case(), now=NOW)
    assert pence["cases"]["recovery"]["return_pct"] == dollars["cases"]["recovery"]["return_pct"]
    assert pence["cases"]["recovery"]["price"] == pytest.approx(dollars["cases"]["recovery"]["price"] * 100)


@pytest.mark.parametrize("change", ["stale", "future_catalyst", "expired_catalyst", "after_target", "old_filing", "old_period", "unsafe_source", "missing_invalidation", "listing_concern", "unsupported_multiple", "not_2x", "unordered"])
def test_missing_or_conflicting_evidence_cannot_become_a_documented_case(change):
    record = reviewed_case()
    if change == "stale": record["reviewed_at"] = "2026-09-01"
    if change == "future_catalyst": record["catalyst"]["expected_by"] = "2028-01-01"
    if change == "expired_catalyst": record["catalyst"]["expected_by"] = "2026-10-21"
    if change == "after_target": record["target_by"] = "2026-12-01"
    if change == "old_filing": record["filing_accession"] = "0000001234-26-000000"
    if change == "old_period": record["statement_periods"]["cashflow"] = "2026-06-30"
    if change == "unsafe_source": record["cause"]["sources"][0]["url"] = "javascript:alert(1)"
    if change == "missing_invalidation": record["catalyst"].pop("invalidation")
    if change == "listing_concern": record["risk_reviews"]["listing_and_corporate_actions"]["status"] = "UNRESOLVED"
    if change == "unsupported_multiple": record["valuation"]["cases"]["recovery"]["sources"] = []
    if change == "not_2x": record["valuation"]["cases"]["recovery"]["equity_fcf_usd"] = 90e6
    if change == "unordered": record["valuation"]["cases"]["bear"]["equity_fcf_multiple"] = 100
    result = assess_recovery_case(stock(), record, now=NOW)
    assert result["status"] == "RESEARCH_WATCH" and result["missing"]


@pytest.mark.parametrize("change", ["old_drop", "unknown_drop", "financial_failure", "source_failure", "no_local_coverage", "cash_burn"])
def test_a_recovery_story_cannot_override_recentness_or_resilience_failures(change):
    data = stock()
    if change == "old_drop": data["price_dislocation"]["recent_peak_age_sessions"] = 100
    if change == "unknown_drop": data["price_dislocation"] = {}
    if change == "financial_failure": data["solvency"]["status"] = "EXCLUDE"
    if change == "source_failure": data["official_filing_check"]["status"] = "UNVERIFIED"
    if change == "no_local_coverage": data["official_filing_check"]["status"] = "NOT_COVERED"
    if change == "cash_burn": data["financial_evidence"]["cashflow"]["values"]["ocf"] = -1
    result = assess_recovery_case(data, reviewed_case(), now=NOW)
    assert result["status"] == "RESEARCH_WATCH" and result["missing"]


def test_three_month_drop_that_has_flattened_can_still_be_recent():
    prices = np.r_[np.repeat(100., 200), np.linspace(100, 65, 30), np.repeat(65., 22)]
    frame = pd.DataFrame({"Close": prices}, index=pd.bdate_range(end="2026-10-22", periods=len(prices)))
    result = drawdown_candidate(frame, load_policy(), now=NOW)
    assert result["screen_cohort"] == "recent_drawdown"
    assert result["drop_21d_pct"] == 0
    assert result["drop_recent_peak_pct"] == pytest.approx(-35)
    assert 0 < result["recent_peak_age_sessions"] <= 63


def test_old_peak_with_small_new_move_is_not_a_recent_fallen_stock():
    frame = pd.DataFrame({"Close": np.r_[np.repeat(100., 100), np.repeat(60., 130), np.linspace(60, 58, 22)]})
    assert drawdown_candidate(frame, load_policy(), now=NOW) is None


def test_stale_and_suspended_price_histories_do_not_qualify():
    frame = pd.DataFrame({"Close": np.linspace(100, 60, 64)}, index=pd.bdate_range(end="2026-09-01", periods=64))
    assert drawdown_candidate(frame, load_policy(), now=NOW) is None
    # Sparse bars can span months despite representing only a few observed sessions.
    frame.index = pd.date_range(end="2026-10-22", periods=64, freq="5D")
    assert drawdown_candidate(frame, load_policy(), now=NOW) is None


def test_recent_window_preserves_missing_rows_and_exact_boundary():
    frame = pd.DataFrame({"Close": np.r_[100., np.repeat(70., 63)]})
    assert drawdown_candidate(frame, load_policy(), now=NOW)["recent_peak_age_sessions"] == 63
    frame.iloc[30] = float("nan")
    assert drawdown_candidate(frame, load_policy(), now=NOW) is None
    assert drawdown_candidate(pd.DataFrame({"Close": np.r_[100., np.repeat(70., 64)]}), load_policy(), now=NOW) is None


def test_reports_separate_documented_cases_from_watches_and_keep_missing_evidence(tmp_path):
    item = stock()
    item["goal_fit"] = assess_recovery_case(item, now=NOW)
    audit = [dict(item, decision="selected")]
    assert candidate_needs_review(item)
    data = write_research_report(audit, [item], str(tmp_path / "report"))
    assert data["documented_12m_tickers"] == [] and data["research_watch_tickers"] == ["TEST"]
    assert "catalyst" in (tmp_path / "recovery_review.md").read_text(encoding="utf-8")
    item["goal_fit"] = assess_recovery_case(item, reviewed_case(), now=NOW)
    data = write_research_report([dict(item, decision="selected")], [item], str(tmp_path / "report"))
    assert data["documented_12m_tickers"] == ["TEST"]
    assert data["research_watch_tickers"] == []


def test_keyword_only_catalyst_remains_watch():
    from scanner_policy import _apply_catalyst_analysis
    data = {"ticker": "TEST", "news_headlines": ["Example reports earnings outlook"],
            "financial_health": {"revenue_growth_yoy": .1}, "piotroski_score": 7}
    chosen = _apply_catalyst_analysis([data])
    assert len(chosen) == 1 and chosen[0]["catalyst_status"] == "WATCH"


def test_documented_email_details_include_case_horizon_invalidation_and_sources():
    data = stock()
    data["solvency"].update(flags=[], missing=[], review=[], metrics={})
    data["goal_fit"] = assess_recovery_case(data, reviewed_case(), now=NOW)
    html = financial_detail_html(data)
    assert "DOCUMENTED_12M_CASE" in html and "2027-10-01" in html
    assert "Thesis fails if" in html and "fixture-disclosure" in html
    assert "reverse arithmetic, not a forecast" in html


def test_documented_case_ranks_before_a_watch_without_loosening_risk_cutoffs():
    from fallen_angel_scanner import narrow_analyzed_results
    watch = {"ticker": "WATCH", "risk_score": 1, "solvency_status": "SCREEN_PASS", "recovery_potential": 200}
    documented = {"ticker": "CASE", "risk_score": 3, "solvency_status": "REVIEW", "recovery_potential": 50,
                  "goal_fit": {"status": "DOCUMENTED_12M_CASE"}}
    assert narrow_analyzed_results([watch, documented], 1) == [documented]
