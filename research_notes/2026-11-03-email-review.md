# November 3 email review

Reviewed the report generated November 3, 2026 at 01:41 UTC, using the
November 2 trading session. No documented recovery case or research watch
was selected. No holding or investment recommendation is added by this review.

## Coverage and interpretation

The current saved scan processed 1,699 configured symbols, produced 330
price-screen candidates and recorded 50 data gaps. The October 30 comparison
had 368 candidates and nine gaps. Fewer candidates therefore cannot be read
as evidence that there are fewer opportunities in the market.

The 50 gaps comprise 41 currency-verification failures, four price-history
errors and five insufficient histories. All 39 configured .DE symbols are
among the currency failures; the other two are LBRDK and CWEN-A. Price-history
errors affected ZS, RGLD, SNX and WMT. Error class alone does not distinguish
an invalid price bar from another ValueError; no invented price repair is made.

An isolated live check on November 3 successfully fetched EURUSD=X
(1.1200717688, dated November 3) and SAP.DE's EUR quote and market cap.
This establishes present availability for that probe, not restored coverage
for all 39 names or the original failure's cause. A common FX failure is a
plausible explanation for the concentration, but the saved coverage does not
prove it. Previously one failed FX lookup was cached for the entire run.
The loader now retries once before caching failure. Both attempts retain the
same finite, positive, nonfuture, seven-day freshness requirements. Successful
rates remain cached and persistent failures do not trigger per-stock retries.

The growth shadow examined only 12 of 330 candidates: two observations,
nine nonmatches and one unverified; 318 were deferred. These outcomes cannot
establish the absence of other opportunities or an investment success rate.
The 39 price alerts compare old saved baselines and are not new selections.

## DY: reconcile fiscal dates before treating the warning as stale evidence

The shadow observed $224.202, about 48.2% below its recent price peak, with
provider net debt/EBITDA approximately 2.99. This is close to the policy's
3.0 limit and needs funding review rather than a safety label.

Yahoo labels the latest quarter July 31; the SEC filing uses August 1.
The filing confirms cash of $340.080 million, matching the provider snapshot.
This supports investigating a fiscal-date labeling discrepancy, but does not
verify every quarterly/TTM field or authorize a blanket date tolerance.
Debt maturities, covenant headroom, acquisitions, cash conversion and five-year
stress remain unresolved; the filing hold stays active.

The issuer reports 45.6% quarterly revenue growth but 16.7% organic growth.
It also describes wireless revenue deferrals and segment margin pressure.
Acquisition growth cannot be treated as organic growth, and those disclosures
do not establish the cause of the share-price decline or its reversibility.

Sources:
- [August 1 quarter filing](https://www.sec.gov/Archives/edgar/data/67215/000006721526000043/dy-20260801.htm)
- [August 26 results release](https://www.ir.dycomind.com/news-releases/news-release-details/dycom-industries-inc-reports-record-fiscal-2027-second-quarter)

## ECG: pre-acquisition liquidity is insufficient evidence

The shadow's June 30 balance sheet predates September acquisition financing.
The September 8 filing documents refinancing term debt to $477.5 million,
an increase of $200 million, and increasing revolver commitments to $350
million. Facilities and drawn cash must be distinguished. The old balance
sheet's attractive leverage ratios do not clear the post-transaction business.
Reconcile Epsilon consideration, current cash/debt, covenants, maturities,
integration cash and valuation before considering admission. Hold retained.

Source: [September 8 financing filing](https://www.sec.gov/Archives/edgar/data/2015845/000201584526000056/ecg-20260901.htm).

## Next disclosure checkpoints

ASBIS remains scheduled for November 5 and TTD for November 9 under the
existing sourced watch configuration. Sanmina's October 19 announcement now
confirms its fiscal 2026 results call for November 9 at 5 PM Eastern. Updated
SANM's watch to November 9 / fiscal period October 3. An expected release date
does not promise that the annual SEC filing will arrive the same day.

Source: [Sanmina call announcement](https://ir.sanmina.com/news/news-details/2026/SANMINA-CORPORATION-INVITES-YOU-TO-JOIN-ITS-FOURTH-QUARTER-AND-FISCAL-YEAR-2026-EARNINGS-CONFERENCE-CALL/default.aspx).

The practical priority is review of these disclosures and the two new leads,
plus checking the next scan's German-market coverage. No thresholds are
relaxed to manufacture selections. There is still no completed sourced case
supporting both the 50% recovery objective and the five-year resilience review.
