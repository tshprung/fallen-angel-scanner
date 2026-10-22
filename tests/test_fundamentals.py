from copy import deepcopy
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from fundamental_analysis import (load_policy, collect_evidence, assess_solvency,
                                  valuation_scenarios, authoritative_health)
from research_reporting import financial_detail_html, write_research_report
from screening import drawdown_candidate

NOW = "2026-10-21T12:00:00Z"
INFO = {"sector": "Industrials", "industry": "Industrial Machinery", "financialCurrency": "USD"}


def frame(rows, dates):
    return pd.DataFrame(rows, index=pd.to_datetime(dates)).T


def company():
    quarterly = ["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31"]
    annual = ["2025-12-31", "2024-12-31", "2023-12-31"]
    return SimpleNamespace(
        quarterly_balance_sheet=frame({"Cash And Cash Equivalents": [200e6], "Total Debt": [100e6],
            "Current Debt": [20e6], "Stockholders Equity": [500e6], "Current Assets": [400e6], "Current Liabilities": [200e6]}, quarterly[:1]),
        balance_sheet=frame({"Ordinary Shares Number": [100e6, 100e6]}, annual[:2]),
        quarterly_cashflow=frame({"Operating Cash Flow": [40e6] * 4, "Capital Expenditure": [-15e6] * 4}, quarterly),
        cashflow=frame({"Operating Cash Flow": [160e6] * 3, "Capital Expenditure": [-60e6] * 3}, annual),
        quarterly_income_stmt=frame({"EBIT": [30e6] * 4, "Interest Expense": [2e6] * 4,
            "EBITDA": [40e6] * 4, "Total Revenue": [250e6] * 4}, quarterly),
        income_stmt=pd.DataFrame(),
    )


def evidence():
    return collect_evidence(company(), INFO, now=NOW)


def test_ttm_uses_four_distinct_consecutive_quarters_and_capex_outflows():
    data = evidence()
    assert data["cashflow"]["values"]["fcf"] == 100e6
    assert data["cashflow"]["basis"] == "ttm_quarterly"
    assert len(data["cashflow"]["periods"]) == 4
    assert data["balance"]["asof"] == "2026-09-30"
    assert data["balance"]["rows"]["cash"] == "Cash And Cash Equivalents"


def test_explicit_zero_debt_is_evidence_but_missing_debt_is_not_zero():
    stock = company()
    stock.quarterly_balance_sheet.loc["Total Debt"] = 0
    stock.quarterly_balance_sheet = stock.quarterly_balance_sheet.drop(index="Current Debt")
    data = collect_evidence(stock, INFO, now=NOW)
    assert data["balance"]["values"]["current_debt"] == 0
    assert assess_solvency(data, INFO)["status"] == "SCREEN_PASS"
    stock.quarterly_balance_sheet = stock.quarterly_balance_sheet.drop(index="Total Debt")
    data = collect_evidence(stock, INFO, now=NOW)
    assert assess_solvency(data, INFO)["status"] == "UNVERIFIED"


def test_stale_statement_does_not_receive_a_pass():
    data = evidence()
    data["balance"]["age_days"] = 300
    assert assess_solvency(data, INFO)["status"] == "UNVERIFIED"


def test_missing_cash_is_not_treated_as_zero_or_financially_safe():
    data = evidence()
    data["balance"]["values"]["cash"] = None
    assert assess_solvency(data, INFO)["status"] == "UNVERIFIED"


def test_missing_interest_with_debt_is_unverified():
    data = evidence()
    data["income"]["values"]["interest"] = None
    result = assess_solvency(data, INFO)
    assert result["status"] == "UNVERIFIED"
    assert any("interest" in message for message in result["missing"])


@pytest.mark.parametrize("interest", [100e6, -100e6])
def test_interest_sign_conventions_produce_the_same_low_coverage_exclusion(interest):
    data = evidence()
    data["income"]["values"]["interest"] = interest
    result = assess_solvency(data, INFO)
    assert result["status"] == "EXCLUDE"
    assert result["metrics"]["interest_coverage"] == pytest.approx(1.2)


def test_cash_burn_with_short_runway_is_excluded():
    data = evidence()
    data["cashflow"]["values"].update(fcf=-200e6, ocf=-100e6)
    result = assess_solvency(data, INFO)
    assert result["status"] == "EXCLUDE"
    assert result["metrics"]["cash_runway_months"] == pytest.approx(12 * 200 / 208)


def test_near_term_refinancing_gap_is_excluded():
    data = evidence()
    data["balance"]["values"].update(cash=5e6, current_debt=100e6)
    assert "adequately" in " ".join(assess_solvency(data, INFO)["flags"])


def test_missing_24_month_schedule_is_visible_review_not_claimed_verified():
    result = assess_solvency(evidence(), INFO)
    assert result["status"] == "REVIEW"
    assert any("13–24" in message for message in result["review"])


@pytest.mark.parametrize("sector,industry", [("Financial Services", "Banks—Regional"),
    ("Financial Services", "Insurance—Life"), ("Real Estate", "REIT—Retail")])
def test_specialist_sectors_cannot_pass_the_operating_company_model(sector, industry):
    result = assess_solvency(evidence(), {"sector": sector, "industry": industry})
    assert result["status"] == "SPECIALIST_REVIEW"
    assert result["missing"]


def test_quarter_gap_falls_back_to_dated_annual_instead_of_partial_ttm():
    stock = company()
    stock.quarterly_cashflow = stock.quarterly_cashflow.drop(columns=pd.Timestamp("2026-03-31"))
    data = collect_evidence(stock, INFO, now=NOW)
    assert data["cashflow"]["basis"] == "annual"
    assert data["cashflow"]["values"]["fcf"] == 100e6
    assert assess_solvency(data, INFO)["status"] == "UNVERIFIED"  # annual period is stale


def test_future_statements_are_not_used():
    stock = company()
    stock.quarterly_balance_sheet.columns = pd.to_datetime(["2027-01-01"])
    stock.balance_sheet = pd.DataFrame()
    assert collect_evidence(stock, INFO, now=NOW)["balance"]["basis"] == "unavailable"


def test_fcf_scenarios_use_equity_multiple_without_subtracting_debt_twice():
    result = valuation_scenarios(evidence(), INFO, 10, 1e9, 1)
    assert result["status"] == "SENSITIVITY"
    assert result["normalized_fcf_usd"] == 92e6
    assert result["cases"]["base"]["price"] == pytest.approx(10 * 1.38 / 1.05)
    assert result["cases"]["bear"]["price"] < result["cases"]["base"]["price"] < result["cases"]["bull"]["price"]
    assert result["plausible_upside_screen"]


def test_deteriorating_current_cashflow_caps_normalized_earnings_power():
    data = evidence()
    data["cashflow"]["values"]["fcf"] = 50e6
    assert valuation_scenarios(data, INFO, 10, 1e9, 1)["normalized_fcf_usd"] == 42e6


def test_an_unprofitable_year_prevents_false_normalization():
    data = evidence()
    data["annual_fcf"][1]["fcf"] = -1
    assert valuation_scenarios(data, INFO, 10, 1e9, 1)["status"] == "UNAVAILABLE"


def test_quote_price_units_and_financial_currency_do_not_change_valuation_return():
    data = evidence()
    dollar = valuation_scenarios(data, INFO, 10, 1e9, 1)
    pence = valuation_scenarios(data, INFO, 1000, 1e9, 1)
    assert pence["cases"]["base"]["return_pct"] == dollar["cases"]["base"]["return_pct"]
    assert pence["cases"]["base"]["price"] == pytest.approx(100 * dollar["cases"]["base"]["price"])
    converted = deepcopy(data)
    converted["cashflow"]["values"]["fcf"] /= 2
    converted["income"]["values"]["interest"] /= 2
    for year in converted["annual_fcf"]:
        year["fcf"] /= 2
    assert valuation_scenarios(converted, INFO, 10, 1e9, 2)["cases"] == dollar["cases"]


def test_statement_health_replaces_quote_defaults_consistently_in_usd():
    data = evidence()
    result = authoritative_health({"cash": 1, "debt_to_equity": .5}, data, 2, 1e9)
    assert result["cash"] == 400e6
    assert result["net_debt"] == -200e6
    assert result["debt_to_equity"] == .2
    assert result["current_ratio"] == 2


def test_old_drawdown_that_stabilized_is_not_missed():
    history = pd.DataFrame({"Close": np.r_[np.linspace(100, 60, 220), np.repeat(60., 32)]})
    assert drawdown_candidate(history, load_policy())["screen_cohort"] == "stabilizing_drawdown"


def test_exactly_21_price_intervals_identify_recent_shock():
    assert drawdown_candidate(pd.DataFrame({"Close": np.linspace(100, 70, 22)}), load_policy())["screen_cohort"] == "recent_shock"
    assert drawdown_candidate(pd.DataFrame({"Close": np.linspace(100, 70, 21)}), load_policy()) is None


def test_financial_detail_escapes_external_text_and_labels_assumptions():
    data = evidence()
    solvency = assess_solvency(data, INFO)
    solvency["review"].append("<script>bad</script>")
    stock = {"currency": "USD", "financial_evidence": data, "solvency": solvency,
             "valuation": valuation_scenarios(data, INFO, 10, 1e9, 1)}
    html = financial_detail_html(stock)
    assert "<script>" not in html
    assert "No probabilities assigned" in html
    assert "not a one-year forecast" in html


def test_report_preserves_unverified_candidates_with_reasons(tmp_path):
    item = {"ticker": "AAA", "decision": "unverified", "solvency": {"status": "UNVERIFIED", "missing": ["Current debt"]}}
    write_research_report([item], [], str(tmp_path / "report"))
    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert data["candidates"][0]["solvency"]["missing"] == ["Current debt"]


def test_unordered_valuation_policy_fails_validation(tmp_path):
    policy = load_policy()
    policy.pop("id")
    policy["valuation"]["bear"]["equity_fcf_multiple"] = 100
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="ordered"):
        load_policy(path)


def test_missing_interest_cannot_produce_a_financing_adjusted_valuation():
    data = evidence()
    data["income"]["values"]["interest"] = None
    assert valuation_scenarios(data, INFO, 10, 1e9, 1)["status"] == "UNAVAILABLE"


def test_statement_date_mismatch_is_visible():
    data = evidence()
    data["income"]["asof"] = "2025-12-31"
    assert any("align" in message for message in assess_solvency(data, INFO)["missing"])


@pytest.mark.parametrize("filing_status,blocked", [("METADATA_CHECKED", False), ("NOT_COVERED", False),
                                                    ("UNVERIFIED", True), ("REVIEW_REQUIRED", True)])
def test_stage2_uses_statements_and_fcf_instead_of_a_price_rebound(monkeypatch, filing_status, blocked):
    import fallen_angel_scanner as scanner
    stock = company()
    stock.history = lambda **kwargs: pd.DataFrame({"Close": np.repeat(10., 252)})
    info = dict(INFO, currency="USD", marketCap=1e9, longName="Example")
    data = evidence()
    monkeypatch.setattr(scanner, "get_stock_with_retry", lambda _: (stock, info))
    monkeypatch.setattr(scanner, "should_send_stock", lambda *args: True)
    monkeypatch.setattr(scanner, "profitability_signals", lambda _: (0, False))
    monkeypatch.setattr(scanner, "analyze_price_shape", lambda *args: {"shape": "choppy", "stable_years": 3, "recent_drop_pct": -35})
    monkeypatch.setattr(scanner, "get_financial_health", lambda _: {})
    monkeypatch.setattr(scanner, "collect_evidence", lambda *args, **kwargs: data)
    monkeypatch.setattr(scanner, "check_sec_filings", lambda *args, **kwargs: {
        "status": filing_status, "blocks_selection": blocked, "findings": ["Fixture filing review"]})
    monkeypatch.setattr(scanner, "compute_piotroski_score", lambda *args: (8, 9))
    monkeypatch.setattr(scanner, "get_earnings_date", lambda _: (None, None))
    monkeypatch.setattr(scanner, "search_recent_news", lambda *args: [])
    monkeypatch.setattr(scanner, "calculate_risk_score", lambda *args, **kwargs: 2)
    monkeypatch.setattr(scanner, "detect_bottom", lambda *args: (True, 9, 10, "LOW"))
    def no_rebound_targets(*args, **kwargs):
        raise AssertionError("Historical price target must not determine value")
    monkeypatch.setattr(scanner, "estimate_recovery_target", no_rebound_targets)
    chosen, _ = scanner.stage2_deep_analysis([{"ticker": "AAA", "current_price": 10, "drop_21d_pct": 0}], {})
    if blocked:
        assert chosen == []
        audit = scanner._last_research_audit[0]
        assert audit["decision"] == ("filing_unverified" if filing_status == "UNVERIFIED" else "filing_review")
        assert "valuation" not in audit
        return
    assert len(chosen) == 1
    assert chosen[0]["target_basis"] == "fcf_sensitivity"
    assert chosen[0]["solvency_status"] == "REVIEW"
    assert chosen[0]["financial_health"]["cash"] == 200e6
    assert scanner._last_research_audit[0]["decision"] == "selected"


def test_missing_solvency_evidence_cannot_be_offset_by_good_technicals(monkeypatch):
    import fallen_angel_scanner as scanner
    data = evidence()
    data["balance"]["values"]["cash"] = None
    info = dict(INFO, currency="USD", marketCap=1e9)
    monkeypatch.setattr(scanner, "get_stock_with_retry", lambda _: (company(), info))
    monkeypatch.setattr(scanner, "should_send_stock", lambda *args: True)
    monkeypatch.setattr(scanner, "profitability_signals", lambda _: (0, False))
    monkeypatch.setattr(scanner, "analyze_price_shape", lambda *args: {"shape": "sudden_drop"})
    monkeypatch.setattr(scanner, "get_financial_health", lambda _: {})
    monkeypatch.setattr(scanner, "collect_evidence", lambda *args, **kwargs: data)
    def technicals_must_not_override_missing_data(*args, **kwargs):
        raise AssertionError("Must stop before technical scoring")
    monkeypatch.setattr(scanner, "calculate_risk_score", technicals_must_not_override_missing_data)
    assert scanner.stage2_deep_analysis([{"ticker": "AAA", "current_price": 10}], {}) == ([], [])
    assert scanner._last_research_audit[0]["decision"] == "unverified"
