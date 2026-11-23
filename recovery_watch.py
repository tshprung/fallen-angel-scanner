"""Recovery-watch preview CLI. Writes email files locally; never connects to SMTP."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import SMTP
from html import escape
import json
import math
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from ai_research import atomic_json, MAX_SHORTLIST
from fallen_angel_scanner import (debt_filter_applies, is_biotechnology_company, is_tradeable_equity,
                                 not_penny_delist_risk, passes_avg_dollar_liquidity,
                                 profitability_signals, should_exclude_for_leverage)
from recovery_prices import NY, SECTOR_FUNDS, bounce_status, collect, distribution_adjusted_close, drop_events, read_bars
from review_holds import load_review_holds
from tickers_config import get_min_market_cap_usd
from paper_sessions import next_paper_session

def latest_session(now):
    # Wait for the normal close even on early-close days. A missing feed bar never rolls the date back.
    local = now.astimezone(NY)
    day = local.date() if local.hour >= 16 else local.date()-timedelta(days=1)
    for _ in range(10):
        prior = pd.Timestamp(str(day-timedelta(days=1)), tz=NY) + pd.Timedelta(hours=12)
        check, _ = next_paper_session("SPY", prior, pd.Timestamp(now))
        if check == day:
            return day
        day -= timedelta(days=1)
    raise ValueError("US exchange calendar unavailable")

def peer_fund(info):
    if "semiconductor" in info.get("industry","").lower():
        return "SOXX"
    return SECTOR_FUNDS.get(info.get("sector"))

def research_hold(info, known=None):
    if known:
        return known["reason"]
    if not info.get("sector") or not info.get("industry"):
        return "Industry classification missing. Financial risk unverified."
    if not debt_filter_applies(info):
        return "Specialist review required. Deposit funding, credit losses or sector-specific financing need separate analysis."
    excluded, reason = should_exclude_for_leverage(info)
    if excluded:
        if reason.startswith("High debt") and not (info.get("totalStockholderEquity") or 0) > 0:
            return "Leverage unverified. Confirm debt and book equity from the same balance sheet."
        return reason
    if profitability_signals(info)[1]:
        return "Financial exclusion: negative margins, negative operating cash flow and declining revenue."
    return None

def eligible(info, symbol, bars, liquidity_floor):
    cap = info.get("marketCap")
    if not cap or not math.isfinite(cap) or not info.get("industry") or not info.get("exchange"):
        raise ValueError("Missing capitalization or listing evidence")
    return (info.get("symbol")==symbol and info.get("currency")=="USD" and info.get("quoteType")=="EQUITY"
            and is_tradeable_equity(info) and not is_biotechnology_company(info)
            and not_penny_delist_risk(dict(info,regularMarketPrice=float(bars.Close.iloc[-1])),symbol)
            and cap >= get_min_market_cap_usd(symbol) and passes_avg_dollar_liquidity(bars,liquidity_floor))

def fetch_profile(ticker):
    return yf.Ticker(ticker).get_info()

def scan(directory, cache, state, now, profile=fetch_profile):
    from scanner_policy import get_min_avg_dollar_volume_usd_with_extension, _load_extension
    universe = json.loads(Path("scan_coverage.json").read_text())
    symbols = sorted({s for s in universe["requested_symbols"] if "." not in s})
    end = latest_session(now)
    folder, failures = collect(symbols+list(SECTOR_FUNDS.values())+["SOXX","SPY"],end,cache)
    calendar = read_bars(folder,"SPY").index
    if calendar[-1].date()!=end or len(calendar)<284:
        raise ValueError("Missing completed benchmark session or lookback")
    previous = state.get("last_scan")
    if previous and date.fromisoformat(previous)>end:
        raise ValueError("Watch state is newer than this scan")
    # Recheck a month for source gaps, deferred alerts and new signals after downtime.
    start = min(pd.Timestamp(previous),calendar[-21]) if previous else calendar[-21]
    known = load_review_holds()
    positives = {}
    for ticker in symbols:
        if ticker in failures:
            continue
        try:
            bars = read_bars(folder,ticker)
            if bars.empty or bars.index[-1]!=calendar[-1]:
                raise ValueError("Last close missing")
            if bars.reindex(calendar[-21:]).Close.isna().any():
                raise ValueError("Incomplete recent price history")
            events = drop_events(bars,calendar,start)
            if events:
                positives[ticker] = (events[-1],bars)
        except (ValueError,KeyError,IndexError) as exc:
            failures[ticker] = str(exc)
    _load_extension()
    def enrich(item):
        ticker,(event,bars) = item
        try:
            info = profile(ticker)
            if not eligible(info,ticker,bars,get_min_avg_dollar_volume_usd_with_extension(ticker)):
                return ticker,None,None
            comparable = peer_fund(info)
            peer_move = None
            if comparable and comparable not in failures:
                peer = distribution_adjusted_close(read_bars(folder,comparable))
                first,last = pd.Timestamp(event["peak_day"]),pd.Timestamp(event["day"])
                if first in peer and last in peer:
                    peer_move=round(100*(peer[last]/peer[first]-1),1)
                    if not math.isfinite(peer_move):
                        peer_move=None
            key=ticker+"@"+event["day"]
            event.update(ticker=ticker, name=info.get("shortName") or ticker, key=key, cap=info["marketCap"],
                         sector=info["sector"], peer=comparable, peer_move=peer_move, hold=research_hold(info,known.get(ticker)),
                         latest_close=float(bars.Close.iloc[-1]), latest_day=end.isoformat())
            return ticker,event,None
        except Exception as exc:
            return ticker,None,type(exc).__name__+": "+str(exc)[:140]
    watch=state.setdefault("watch",{})
    with ThreadPoolExecutor(max_workers=3) as pool:
        for ticker,event,error in pool.map(enrich,positives.items()):
            if error: failures[ticker]=error
            if event: watch[event["key"]]=event
    # Refresh previously alerted prices while waiting for a filing; retire old episodes.
    for key,event in list(watch.items()):
        ticker=event["ticker"]
        if (end-date.fromisoformat(event["day"])).days>45:
            del watch[key]
        elif ticker in failures or ticker not in symbols:
            event["latest_close"]=None
            event["chart"]="Current closing history unavailable."
        elif ticker in symbols:
            bars=read_bars(folder,ticker)
            if bars.index[-1]==calendar[-1]:
                event.update(latest_close=float(bars.Close.iloc[-1]),latest_day=end.isoformat(),
                             chart=bounce_status(bars,calendar,event["day"]))
    state["last_scan"]=end.isoformat()
    coverage=dict(date=end.isoformat(), universe_date=universe["started_at"][:10], requested=len(symbols),
                  gaps={s:e for s,e in failures.items() if s in symbols}, raw_crossings=len(positives))
    atomic_json(directory/"coverage.json",coverage)
    return coverage

def ranked(events):
    return sorted(events,key=lambda e:(e["day"],e["cap"],e["ticker"]),reverse=True)

def available_today(state, ticker, day):
    audience=state.get("audience",{}).get(day,[])
    return ticker in audience or len(audience)<MAX_SHORTLIST

def record_audience(state, rows, day):
    audience=state.setdefault("audience",{}).setdefault(day,[])
    audience.extend(e["ticker"] for e in rows if e["ticker"] not in audience)

def early_batch(state, day):
    seen=set(state.get("early_seen",[]))
    latest={}
    for event in ranked(state["watch"].values()):
        latest.setdefault(event["ticker"],event)
    audience=set(state.get("audience",{}).get(day,[]))
    rows=[]
    for event in latest.values():
        if event["key"] in seen or not event.get("latest_close"):
            continue
        if event["ticker"] not in audience and len(audience)>=MAX_SHORTLIST:
            continue
        rows.append(event)
        audience.add(event["ticker"])
    return rows[:MAX_SHORTLIST]

def money(v):
    return f"${v:,.2f}"

def compose(directory, kind, rows, coverage, now):
    subject=f"Recovery watch | {len(rows)} " + ("price alerts" if kind=="early" else "research updates")
    parts=[f"<h1>{escape(subject)}</h1>",f"<p>US pilot · Completed session {coverage['date']}. "
           f"{coverage['requested']} symbols from the {coverage['universe_date']} scanner list; "
           f"{len(coverage['gaps'])} data gaps.</p>"]
    if not rows:
        parts.append("<p>No new updates for this preview.</p>")
    for e in rows:
        parts.append(f"<h2>{escape(e['name'])} ({escape(e['ticker'])})</h2>")
        parts.append(f"<p>{e['day']} close {money(e['close'])}, down {abs(e['drop']):.1f}% from "
                     f"{money(e['reference'])} on {e['peak_day']}. A 40% gain from the alert close requires "
                     f"<b>{money(e['close']*1.4)}</b>.</p>")
        span=e.get("range")
        parts.append("<p>"+(f"Prior 252-session closing range {money(span[0])}–{money(span[1])}."
                             if span else "Prior-year stability unverified.")+" "+
                     (f"Sector comparison: {escape(e['peer'])} {e['peer_move']:+.1f}% over the same dates."
                      if e.get("peer_move") is not None else "Comparable-sector history unavailable.")+"</p>")
        parts.append("<p>Chart through "+escape(e["latest_day"])+". "+escape(e.get("chart","Closing pattern unverified."))+"</p>")
        if kind=="early":
            parts.append(f"<p><b>{'Research hold' if e.get('hold') else 'Research pending'}</b>. "+
                         escape(e.get("hold") or "The price trigger alone does not establish financial safety or fair value.")+"</p>")
            if e["latest_day"]!=e["day"] and e.get("latest_close"):
                parts.append(f"<p>Latest completed close {money(e['latest_close'])} on {e['latest_day']}; "
                             f"40% hurdle now {money(1.4*e['latest_close'])}.</p>")
        else:
            parts.append("<p>Cause of this specific drop: unverified. The filing review covers operating and financing evidence.</p>")
            parts.append(f"<p><b>{escape(e['status'])}</b></p><p>{escape(e['brief']).replace(chr(10),'<br>')}</p>")
            quote=e.get("quote")
            if quote:
                price=quote["price"]
                parts.append(f"<p>Price at {escape(quote['at'])}: <b>{money(price)}</b>. "
                             f"40% gain now requires <b>{money(price*1.4)}</b>. Return to the old "
                             f"reference would be {100*(quote['reference']/price-1):+.1f}%. "
                             "The reference is historical, not a fair-value estimate.</p>")
            else:
                parts.append("<p>Fresh comparable price unavailable. Current upside unverified.</p>")
            for label,url in e.get("sources",[]):
                parts.append(f'<p><a href="{escape(url,quote=True)}">{escape(label)}</a></p>')
    body="<!doctype html><html lang='en'><meta charset='utf-8'><body style='font:16px/1.5 Arial,sans-serif;max-width:720px;margin:24px auto'>"+ "".join(parts)+"</body></html>"
    msg=EmailMessage(policy=SMTP)
    msg["Subject"]=subject
    from lxml import html
    msg.set_content(html.fromstring(body.replace("</p>","</p>\n").replace("</h2>","</h2>\n")).text_content())
    msg.add_alternative(body,subtype="html")
    (directory/(kind+".eml")).write_bytes(msg.as_bytes())
    (directory/(kind+".html")).write_text(body,encoding="utf-8")
    atomic_json(directory/(kind+".json"), {"generated_at":now.isoformat(),"rows":rows})

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=["early","followup"])
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--state",type=Path,required=True)
    parser.add_argument("--cache",type=Path,default=Path("data/watch-prices"))
    parser.add_argument("--repeat-preview",action="store_true",help="Re-render today's early alerts for preview inspection")
    args=parser.parse_args()
    now=datetime.now(timezone.utc)
    args.out.mkdir(parents=True,exist_ok=True)
    state=json.loads(args.state.read_text()) if args.state.exists() else {}
    if args.stage=="early":
        coverage=scan(args.out,args.cache,state,now)
        day=now.astimezone(NY).date().isoformat()
        rows=early_batch(state,day)
        if args.repeat_preview and state.get("audience",{}).get(day):
            audience=set(state["audience"][day])
            repeat=[e for e in ranked(state["watch"].values()) if e["ticker"] in audience
                    and e["key"] in state.get("early_seen",[]) and e.get("latest_close")]
            by_ticker={e["ticker"]:e for e in reversed(ranked(rows+repeat))}
            rows=ranked(by_ticker.values())[:MAX_SHORTLIST]
        compose(args.out,"early",rows,coverage,now)
        state["early_seen"]=list(dict.fromkeys(state.get("early_seen",[])+[e["key"] for e in rows]))
    else:
        from recovery_followup import followup
        coverage=json.loads((args.out/"coverage.json").read_text())
        rows=followup(state,now)
        compose(args.out,"followup",rows,coverage,now)
        state.setdefault("reviewed",{}).update({e["key"]:e["fingerprint"] for e in rows})
    record_audience(state,rows,now.astimezone(NY).date().isoformat())
    atomic_json(args.state,state)
    print(f"{args.stage} preview: {len(rows)} updates: "+", ".join(e["ticker"] for e in rows))

if __name__=="__main__":
    main()
