from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
import json

import pandas as pd
import pytest

import recovery_followup as research
import recovery_watch as watch
from recovery_prices import bounce_status, drop_events, historical_reference
from sec_filings import SourceUnavailable

NOW = datetime(2026,11,23,15,tzinfo=timezone.utc)
# Daily NVDA closes as published for Oct 20–Nov 20. No Monday bar is an input.
NVDA = [216.47,221.97,212.21,210.96,216,217.94,215.38,213.66,204.64,202.06,206.69,
        200.13,181.60,186.64,178.67,168.89,173.73,166.19,162.85,156.14,155.46,150.96,145.98,125.53]

def bars(values, start="2026-10-20"):
    return pd.DataFrame({"Close":values,"Adj Close":values},index=pd.bdate_range(start,periods=len(values)))

def nvda():
    h=bars(NVDA)
    e,=drop_events(h,h.index,h.index[0])
    return dict(e,ticker="NVDA",key="NVDA@"+e["day"],cap=1e12,name="NVIDIA",peer="SOXX",peer_move=None,
                latest_day=e["day"],latest_close=e["close"],hold=None)

def preview(tmp_path,kind,rows):
    watch.compose(tmp_path,kind,rows,{"date":"2026-11-20","universe_date":"2026-11-12","requested":1,"gaps":{}},NOW)
    message=BytesParser(policy=policy.default).parsebytes((tmp_path/(kind+".eml")).read_bytes())
    return message.get_body(("html",)).get_content()

def test_nvda_replay_and_email(tmp_path):
    h=bars(NVDA)
    assert not drop_events(h.iloc[:-1],h.index[:-1],h.index[0])
    e=nvda()
    assert (e["day"],e["peak_day"],e["drop"])==("2026-11-20","2026-11-06",-32.74)
    assert watch.latest_session(NOW).isoformat()==e["day"]
    assert "Research pending" in preview(tmp_path,"early",[e])
    update=dict(e,brief="Filing evidence under review.",status="Research hold",quote={"price":167.04,"at":"2026-11-23 open","reference":186.64})
    html=preview(tmp_path,"followup",[update])
    assert "$233.86" in html and "+11.7%" in html

def test_missing_sessions_and_distributions():
    h=bars([100.]*12+[65.]*3)
    assert len(drop_events(h,h.index,h.index[0]))==1
    assert not drop_events(h.drop(h.index[9]),h.index,h.index[0])
    h["Adj Close"]=65.
    h["Dividends"]=0.
    h.iloc[1,h.columns.get_loc("Dividends")]=.01
    assert not drop_events(h,h.index,h.index[0])


def test_multiyear_reference_separates_spikes_from_repeated_prices():
    index = pd.bdate_range("2020-01-01","2025-02-28")
    b = pd.DataFrame({"Close":50., "Adj Close":50.},index=index)
    peak = {"peak_day":"2025-02-10"}
    b.loc["2025-02":] = 100.
    for year in (2021,2024):
        b.loc[f"{year}-04":f"{year}-06"] = 100.
    result = historical_reference(b,index,peak)
    assert result == {"months":60,"near":6,"years_with_three":2}
    assert historical_reference(b.drop(pd.Timestamp("2023-10-31")),index,peak) is None
    recent = historical_reference(b.loc["2024-07":],index,peak)
    assert recent["months"] == 7 and recent["years_with_three"] == 0
    e = dict(nvda(),latest_close=65., latest_reference=100., near_reference_sessions=20)
    spike = dict(e,ticker="SPIKE",near_reference_sessions=100,
                 long_history={"months":60,"near":10,"years_with_three":1})
    repeated = dict(e,long_history=result)
    assert watch.ranked([spike,repeated]) == [repeated,spike]


def test_history_counts_only_complete_pre_drop_year():
    h=bars([80.]*212+[100.]*40+[100.]*10+[65.])
    event,=drop_events(h,h.index,h.index[-1])
    assert event["near_reference_sessions"]==40
    for frame in (h.drop(h.index[5]), h.iloc[1:]):
        event,=drop_events(frame,h.index,h.index[-1])
        assert event["near_reference_sessions"] is None


def test_shortlist_prioritizes_repeated_prices_with_room_to_recover(tmp_path):
    base=dict(nvda(), latest_close=70., latest_reference=100., near_reference_sessions=50)
    held=dict(base,ticker="HOLD",hold="Needs financial review")
    spike=dict(base,ticker="SPIKE",near_reference_sessions=0)
    rebounded=dict(base,ticker="BOUNCE",latest_close=90.,near_reference_sessions=100)
    assert watch.ranked([held,spike,rebounded,base])==[base,spike,rebounded,held]
    mail=preview(tmp_path,"early",[base])
    assert "50/252" in mail and "+42.9%" in mail and "$98.00" in mail

def test_unchanged_alert_and_daily_cap():
    e=nvda()
    state={"watch":{e["key"]:e}}
    day="2026-11-23"
    assert watch.early_batch(state,day)==[e]
    state["early_seen"]=[e["key"]]
    assert not watch.early_batch(state,day)
    state["early_seen"]=[]
    state["audience"]={day:[str(i) for i in range(10)]}
    assert not watch.early_batch(state,day)


def test_bounce_uses_completed_sessions_only():
    h=bars([100.,90.,95.,98.])
    day=h.index[0]
    assert "No completed" in bounce_status(h,h.index[:1],day)
    assert "at the post-alert low" in bounce_status(h,h.index[:2],day)
    assert "unconfirmed" in bounce_status(h,h.index[:3],day)
    assert "two consecutive higher" in bounce_status(h,h.index,day)
    assert "incomplete" in bounce_status(h.drop(h.index[1]),h.index,day)


def test_vendor_debt_units_do_not_support_high_debt_claim():
    info={"sector":"Technology","industry":"Semiconductors","debtToEquity":14.31,"totalDebt":100}
    assert "Leverage unverified" in watch.research_hold(info)
    assert "High debt" in watch.research_hold(dict(info,totalStockholderEquity=7))

def test_first_republic_specialist_hold(tmp_path,monkeypatch):
    # First Republic's March 16 disclosure described $30B of deposits, no equity injection.
    # Historical symbol identity and bank classification suffice for the specialist route.
    hold=watch.research_hold({"industry":"Banks - Regional","sector":"Financial Services"})
    e=dict(nvda(),name="First Republic Bank",ticker="FRC",day="2023-03-17",key="FRC@2023-03-17",
           peak_day="2023-03-16",reference=34.27,close=23.03,drop=-32.8,hold=hold,peer="KRE",peer_move=-6.0)
    state={"watch":{e["key"]:e},"early_seen":[e["key"]]}
    monkeypatch.setattr(research,"evidence",lambda *a:pytest.fail("Bank must not receive ordinary corporate review"))
    monkeypatch.setattr(research,"refresh",lambda *a:None)
    row,=research.followup(state,NOW)
    assert row["status"]=="Research hold" and "Deposit funding" in row["brief"]
    assert "Current upside unverified" in preview(tmp_path,"followup",[row])
    state["reviewed"]={e["key"]:row["fingerprint"]}
    assert research.followup(state,NOW)==[]

class CrocsSEC:
    def get_json(self,url):
        if url==research.SEC_MAPPING:
            return {"fields":["cik","ticker"],"data":[[1334036,"CROX"]]},None
        records=[
            ("10-Q","0001334036-25-000085","2025-08-07T20:35:48Z","crox-20250630.htm","2025-06-30",""),
            ("8-K","0001334036-25-000083","2025-08-07T11:01:43Z","crox.htm","2025-08-07","2.02,9.01"),
            ("8-K","0001334036-25-000099","2025-08-11T20:00:00Z","later.htm","2025-08-11","1.03")]
        fields=("form","accessionNumber","acceptanceDateTime","primaryDocument","reportDate","items")
        b=dict(zip(fields,map(list,zip(*records))))
        b["filingDate"]=[d[:10] for d in b["acceptanceDateTime"]]
        return {"cik":1334036,"tickers":["CROX"],"filings":{"recent":b,"files":[]}},None

def test_crocs_guidance_and_acceptance_cutoff(monkeypatch):
    with pytest.raises(SourceUnavailable):
        research.filings_for("CROX",datetime(2025,8,7,20,tzinfo=timezone.utc),CrocsSEC())
    class Documents:
        def __init__(self,sec): pass
        def get(self,row,cik):
            url=row["url"]
            if "index.htm" in url:
                return '<table><tr><td>2</td><td>Exhibit</td><td><a href="release.htm">Release</a></td><td>EX-99.1</td></tr></table>',None
            if "release.htm" in url:
                return "<p>Management Q3 outlook: revenues down approximately 11% to 9% versus Q3 2024.</p>"*3,None
            return ('<div name="dei:TradingSymbol">CROX</div><div name="dei:EntityCentralIndexKey">1334036</div>'
                    '<div name="dei:DocumentPeriodEndDate">June 30, 2025</div>'+'<p>Reported second quarter growth 3.4%.</p>'*6),None
    monkeypatch.setattr(research,"DocumentClient",Documents)
    packet,docs=research.evidence("CROX",datetime(2025,8,8,20,tzinfo=timezone.utc),CrocsSEC())
    assert "11% to 9%" in packet and "3.4%" in packet and len(docs)==2
    assert all("later" not in url for _,url in docs)

def test_missing_evidence_is_a_visible_hold(monkeypatch,tmp_path):
    e=nvda()
    def missing(*a): raise SourceUnavailable("Current reporting period unverified")
    monkeypatch.setattr(research,"evidence",missing)
    monkeypatch.setattr(research,"refresh",lambda *a:None)
    rows=research.followup({"watch":{e["key"]:e},"early_seen":[e["key"]]},NOW)
    assert "Current reporting period unverified" in preview(tmp_path,"followup",rows)

def test_monthly_reservation_and_three_daily_issuers():
    ledger={"months":{"2026-11":2_900_000},"days":{}}
    research.reserve(ledger,"2026-11","2026-11-23","ABC",100_000)
    with pytest.raises(SourceUnavailable): research.reserve(ledger,"2026-11","2026-11-23","ABC",1)
    for s in ("A","B","C"): research.reserve(ledger,"2026-12","2026-12-01",s,50)
    with pytest.raises(SourceUnavailable): research.reserve(ledger,"2026-12","2026-12-01","D",50)
    research.reserve(ledger,"2026-12","2026-12-01","C",50)
