# November 4 email review

Email received November 4 at 00:52 Warsaw, generated November 3 at 23:52 UTC.
The run used code 00b432c and saved state in c67d27d. No new selection is made
by this review; zero selections with missing coverage cannot establish zero
opportunities.

## Coverage deterioration has identified operational causes

The report processed 1,699 symbols but recorded 455 gaps (26.8%): 411 quote-stage
currency failures, 40 currency/security-stage failures and four insufficient
histories. All 39 configured German symbols remain blocked. The other
currency/security failure is LBRDK. This compares with 50 gaps and 330 price
candidates in the preceding report; the current 234 candidates are not a
comparable measure of market opportunity.

[GitHub job logs](https://github.com/tshprung/fallen-angel-scanner/actions/runs/41740293127/job/126279808033)
show two distinct causes:

- SAP.DE and the subsequent German symbols failed because the common EUR FX
  history contained an inconsistent OHLC candle. The prior bounded retry
  repeatedly encountered the same bad historical data.
- Beginning with CWEN-A, Yahoo returned HTTP 401 / Invalid Crumb and access
  errors. Hundreds of later quotes lacked a verified currency. Missing quote
  currency here is a source failure, not an investment exclusion.

A November 4 diagnostic through the original provider factory confirmed a
November 2 EURUSD=X candle with close 1.11568546 below low 1.11572278.
This is outside the existing numerical tolerance. Later candles were valid.
The November 3 isolated probe did not import the full production adapter, so
its successful close-only retrieval did not demonstrate a production fix.

FX retrieval now requests the latest daily candle instead of a month.
Production OHLC checks remain active, as do finite/positive/date/freshness
checks and the two-attempt limit. No bad candle is altered or accepted and
no stale exchange rate is substituted. A live probe importing scanner_entry
verified a dated November 4 EUR rate and a SAP.DE EUR quote through the full
production adapter. This is limited verification, not proof of full-universe
coverage or recovery of the GitHub runner's authentication.

The existing majority-failure guard missed the US outage because it happened
after many successful quotes. Stage 1 now stops after ten consecutive quote
source failures, preserves incomplete coverage, and the main runner aborts
normal email and paper output. A run with this failure will be visibly failed
in Actions; diagnostic artifacts remain available. No automatic extra email
or workflow rerun was triggered by this review. Currency conversion failures
after a successful quote are tracked separately and do not count toward the
consecutive quote threshold. The existing 50% overall failure guard remains.

## New shadow observation: P / Everpure

The issuer confirms P is Everpure, formerly Pure Storage; it is not a new
unrelated company. The saved observation is $117.65, market cap $39.204 billion,
quarterly revenue growth 37.7% and buffered TTM cash flow $127.121 million.
These provider values are observations, not normalized forecasts.

The SEC quarter is August 2 while Yahoo labels July 31. Reported quarterly
revenue of $1,185.898 million and cash of $385.694 million match the provider,
supporting reconciliation of fiscal labels rather than automatic dismissal
as outdated data. The balance sheet's $225.307 million operating leases match
the provider's total-debt figure; leases need separate treatment from funded
borrowings. This does not resolve the complete financial case.

At the saved market cap, a mechanical 50% upside with 5% dilution and a 20x
equity cash-flow multiple would require $3.087 billion annual cash flow,
about 24.3 times the saved buffered figure. This is a sensitivity, not a
justified multiple or prediction. Cash normalization, working-capital effects,
capital investment, dilution, catalyst, comparable historical price and
five-year resilience remain unresolved. No recovery-case admission or hold
clearance is made.

Sources:
- [Issuer ticker announcement](https://www.everpuredata.com/company/newsroom/press-releases/everpure-to-change-ticker-symbol.html)
- [August 2 quarter filing](https://www.sec.gov/Archives/edgar/data/1474432/000147443226000088/pstg-20260802.htm)

## Existing leads

ECG now has a November 3 results 8-K, accession 0002015845-26-000059,
after the June quarter and September acquisition financing. Its June liquidity
figures remain insufficient for post-acquisition clearance. The full new
release and post-close balance sheet were not verified in this review;
issuer/SEC body retrieval was unavailable. No conclusions about the latest
results, survival or expected return are inferred from filing metadata.

ASBIS's configured November 5 checkpoint is tomorrow. TTD and Sanmina remain
configured for November 9. The next complete run must establish whether the
German FX change restores coverage and Yahoo authentication has recovered.
No user input, server deployment or paid API purchase is required for these
changes. Persistent provider access failures would require a separate data
source assessment; the outage guard does not repair authentication.

Validation: 320 offline tests passed, including production-adapter FX candle
checks, clustered outages after a healthy prefix, incomplete checkpoints, and
normal mail/paper suppression. No financial admission threshold was relaxed.
