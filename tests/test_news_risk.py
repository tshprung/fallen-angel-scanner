import pytest


@pytest.mark.parametrize("headline", [
    "Issuer regains compliance and avoids delisting",
    "Exchange withdraws delisting notice",
    "Nasdaq withdrew delisting notice",
    "Issuer regains Nasdaq listing compliance after receiving a delisting warning",
    "SEC investigation closed without enforcement action",
    "Lawsuit dismissed with prejudice",
])
def test_explicit_resolution_is_not_a_structural_penalty_or_catalyst(headline):
    from fallen_angel_scanner import analyze_news_sentiment
    from scanner_policy import _apply_catalyst_analysis
    from scanner_bugfixes import _catalyst_display

    record = {"ticker": "AAA", "news_headlines": [headline]}
    assert "SERIOUS" not in analyze_news_sentiment([headline])[0]
    assert _apply_catalyst_analysis([record]) == [record]
    assert record["cause_class"] == "unclear" and record["catalyst_status"] == "WATCH"
    assert "NO VERIFIED CATALYST" in _catalyst_display(record)[0]


@pytest.mark.parametrize("headlines", [
    ["Issuer may have avoided delisting"],
    ["Issuer avoids delisting for now"],
    ["Nasdaq denies it withdrew delisting notice"],
    ["Issuer avoids delisting until next hearing"],
    ["Regulator disputes claim that Nasdaq withdrew delisting notice"],
    ["Issuer avoids delisting but reports fraud"],
    ["Issuer avoids delisting", "New delisting notice issued"],
    ["Issuer exits bankruptcy"],
    ["SEC investigation closed without enforcement action?", "Company warns of default"],
])
def test_ambiguous_resolution_or_separate_risk_still_blocks(headlines):
    from fallen_angel_scanner import analyze_news_sentiment
    from scanner_bugfixes import _catalyst_display
    from scanner_policy import _apply_catalyst_analysis

    assert "SERIOUS" in analyze_news_sentiment(headlines)[0]
    record = {"ticker": "AAA", "news_headlines": headlines}
    assert _apply_catalyst_analysis([record]) == []
    assert "FUNDAMENTAL RISK" in _catalyst_display(record)[0]
