from copy import deepcopy
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from fundamental_analysis import collect_evidence, load_policy
from growth_recovery import assess_growth, revenue_growth, run_shadow

NOW = pd.Timestamp("2026-10-29T12:00:00Z")
INFO = {"sector": "Technology", "industry": "Software", "financialCurrency": "USD"}
QUARTERS = pd.to_datetime(["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"])


def frame(rows, dates=QUARTERS):
    return pd.DataFrame(rows, index=dates).T


def stock():
    return SimpleNamespace(
        quarterly_balance_sheet=frame({"Cash And Cash Equivalents": [200e6], "Total Debt": [100e6],
            "Current Debt": [20e6], "Stockholders Equity": [500e6],
            "Current Assets": [400e6], "Current Liabilities": [200e6]}, QUARTERS[:1]),
        balance_sheet=frame({"Ordinary Shares Number": [105e6, 100e6]}, pd.to_datetime(["2025-12-31", "2024-12-31"])),
        quarterly_cashflow=frame({"Operating Cash Flow": [40e6]*4, "Capital Expenditure": [-10e6]*4}, QUARTERS[:4]),
        cashflow=frame({"Operating Cash Flow": [160e6, -10e6, 100e6], "Capital Expenditure": [-40e6]*3},
                       pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31"])),
        quarterly_income_stmt=frame({"Total Revenue": [130e6, 125e6, 120e6, 115e6, 100e6],
            "EBIT": [-5e6]*5, "Interest Expense": [2e6]*5, "EBITDA": [10e6]*5}),
        income_stmt=pd.DataFrame())


def inputs():
    company = stock()
    evidence = collect_evidence(company, INFO, now=NOW)
    evidence["annual_share_growth_age_days"] = 302
    return evidence, revenue_growth(company.quarterly_income_stmt, NOW, 200)


def test_growth_cash_generator_can_be_observed_despite_accounting_loss_and_old_negative_fcf():
    evidence, growth = inputs()
    saved = deepcopy(evidence)
    result = assess_growth(evidence, INFO, growth, load_policy())
    assert result["status"] == "OBSERVE_REVIEW_REQUIRED"
    assert result["selection_eligible"] is False
    assert result["review_required"] is True
    assert evidence == saved
    assert growth["growth_pct"] == pytest.approx(30)


@pytest.mark.parametrize("change,expected", [
    (lambda e: e["balance"]["values"].update(cash=None), "UNVERIFIED"),
    (lambda e: e["balance"].update(age_days=201), "UNVERIFIED"),
    (lambda e: e["cashflow"].update(basis="annual"), "UNVERIFIED"),
    (lambda e: e["income"]["values"].update(interest=None), "UNVERIFIED"),
    (lambda e: e.update(annual_share_growth=None), "UNVERIFIED"),
    (lambda e: e.update(annual_share_growth_age_days=451), "UNVERIFIED"),
    (lambda e: e.update(annual_share_growth=.11), "NOT_MATCHED"),
    (lambda e: e["cashflow"]["values"].update(fcf=-1), "NOT_MATCHED"),
    (lambda e: e["balance"]["values"].update(cash=0, current_debt=100e6), "NOT_MATCHED"),
    (lambda e: e["balance"]["values"].update(current_debt=200e6), "UNVERIFIED"),
])
def test_missing_data_and_funding_failures_never_become_observations(change, expected):
    evidence, growth = inputs()
    change(evidence)
    assert assess_growth(evidence, INFO, growth, load_policy())["status"] == expected


def test_slow_growth_and_specialists_do_not_match():
    evidence, growth = inputs()
    assert assess_growth(evidence, INFO, {**growth, "growth_pct": 10}, load_policy())["status"] == "NOT_MATCHED"
    assert assess_growth(evidence, {**INFO, "industry": "Banks"}, growth, load_policy())["status"] == "NOT_MATCHED"


@pytest.mark.parametrize("kind", ["duplicate", "missing_quarter", "bad_revenue", "stale", "future"])
def test_revenue_comparison_requires_fresh_consecutive_past_quarters(kind):
    data = stock().quarterly_income_stmt.copy()
    when = NOW
    if kind == "duplicate":
        data.columns = [QUARTERS[0], QUARTERS[0], *QUARTERS[2:]]
    elif kind == "missing_quarter":
        data = data.drop(columns=QUARTERS[2])
    elif kind == "bad_revenue":
        data.loc["Total Revenue", QUARTERS[-1]] = float("nan")
    elif kind == "stale":
        when = NOW + pd.Timedelta(days=250)
    else:
        when = pd.Timestamp("2026-08-01T00:00Z")
    assert revenue_growth(data, when, 200)["status"] == "UNVERIFIED"


def test_misaligned_growth_and_cashflow_are_unverified():
    evidence, growth = inputs()
    growth["asof"] = "2026-01-31"
    assert assess_growth(evidence, INFO, growth, load_policy())["status"] == "UNVERIFIED"


def test_shadow_preserves_core_holds_errors_and_daily_first_observations(tmp_path):
    candidates = [{"ticker": name, "current_price": 10} for name in ("AAA", "BBB")]
    audit = [{"ticker": "AAA", "decision": "event_review", "review_hold": {"reason": "Unresolved covenant"}}]
    original = deepcopy(audit)
    calls = []
    def fetch(symbol):
        calls.append(symbol)
        if symbol == "BBB":
            raise RuntimeError("Sensitive source response must not be echoed")
        return stock(), INFO
    run_shadow(candidates, audit, fetch, tmp_path, now=NOW)
    report = json.loads((tmp_path/"growth_recovery_shadow.json").read_text())
    rows = {row["ticker"]: row for row in report["records"]}
    assert rows["AAA"]["status"] == "OBSERVE_REVIEW_REQUIRED"
    assert rows["AAA"]["ordinary_solvency"]["status"] == "EXCLUDE"
    assert rows["AAA"]["review_hold"] == audit[0]["review_hold"]
    assert rows["BBB"]["status"] == "SOURCE_ERROR"
    assert rows["BBB"]["reasons"] == ["RuntimeError"]
    assert audit == original
    history_path = tmp_path/"growth_recovery_shadow_history.json"
    initial = history_path.read_bytes()
    snapshot = json.loads(initial)[0]
    assert snapshot["statement_snapshot"]["cashflow"]["asof"] == "2026-09-30"
    run_shadow(candidates, audit, lambda _: (None, {}), tmp_path, now=NOW+pd.Timedelta(hours=1))
    assert history_path.read_bytes() == initial
    assert set(calls) == {"AAA", "BBB"}


def test_budget_rotation_covers_all_names_without_turning_deferrals_into_failures(tmp_path):
    candidates = [{"ticker": f"T{i:02}"} for i in range(25)]
    seen = set()
    for day in range(4):
        calls = []
        def fetch(symbol):
            calls.append(symbol)
            return stock(), INFO
        summary = run_shadow(candidates, [], fetch, tmp_path, now=NOW+pd.Timedelta(days=day))
        assert len(calls) == 12
        assert summary["counts"]["DEFERRED_BUDGET"] == 13
        seen.update(calls)
    assert seen == {item["ticker"] for item in candidates}


def test_empty_run_and_corrupt_history_are_not_silent_successes(tmp_path):
    def no_fetch(_):
        raise AssertionError("Empty candidates cannot request data")
    assert run_shadow([], [], no_fetch, tmp_path, now=NOW)["counts"] == {}
    history = tmp_path/"growth_recovery_shadow_history.json"
    history.write_text("corrupt", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        run_shadow([], [], no_fetch, tmp_path, now=NOW)
    assert history.read_text() == "corrupt"


def test_optional_shadow_failure_does_not_mutate_selections_or_hide_failure(monkeypatch, tmp_path):
    import fallen_angel_scanner as scanner
    import growth_recovery
    monkeypatch.setattr(scanner, "GROWTH_SHADOW_ENABLED", True, raising=False)
    monkeypatch.setattr(scanner, "REPORT_PREFIX", str(tmp_path/"research_report"), raising=False)
    monkeypatch.setattr(scanner, "REPORT_SCOPE", {}, raising=False)
    audit = [{"ticker": "AAA", "decision": "selected"}]
    monkeypatch.setattr(scanner, "_last_research_audit", audit, raising=False)
    def fail(*args, **kwargs):
        raise ValueError("Broken ledger")
    monkeypatch.setattr(growth_recovery, "run_shadow", fail)
    scanner._collect_growth_shadow([])
    assert audit == [{"ticker": "AAA", "decision": "selected"}]
    assert scanner.REPORT_SCOPE["growth_recovery_shadow"]["status"] == "FAILED"
    assert json.loads((tmp_path/"growth_recovery_shadow.json").read_text())["status"] == "FAILED"


def test_email_summary_labels_shadow_separately_and_exposes_failures():
    from research_reporting import decision_summary_html
    summary = decision_summary_html([], {"growth_recovery_shadow": {
        "status": "COLLECTED", "counts": {"OBSERVE_REVIEW_REQUIRED": 2, "SOURCE_ERROR": 3}}})
    assert "2 observations require review" in summary
    assert "3 source errors" in summary
    assert "no return forecast or selection" in summary
    failed = decision_summary_html([], {"growth_recovery_shadow": {"status": "FAILED"}})
    assert "collection: FAILED" in failed
