# November 6 email review

Reviewed the email generated November 6 at 00:12 UTC (01:12 Warsaw), using
the November 5 trading session. Code was 32e3d15; saved scan state cd7778b.
No investment case or selection is added by this review.

## Overnight coverage recovery confirmed

All 1,699 configured symbols were processed; 1,697 quotes loaded. Recorded
gaps fell from 141 to 22, and company-analysis errors fell from one to zero
across 385 candidates. The maximum consecutive quote-failure count was one.
The midnight FX correction therefore worked in the actual overnight run,
not just the preceding daytime probe.

The blanket foreign-market blockage is gone. Remaining non-US gaps are
CRDA.L, ICL.TA, ALV.DE, PUM.DE, FRE.DE and CON.DE. All 26 Polish symbols
completed Stage 1 without a recorded source gap; Germany had four gaps out
of 39, the UK one out of 48 and Israel one out of 19. No recorded source gap
does not establish complete, correct financial evidence or investment fitness.
The other 16 gaps are US symbols. Overall gap categories: eleven
currency/security failures, nine insufficient histories, and two quote failures.

There are 385 candidates rather than the prior 277, but improved coverage
and market-price changes prevent attributing that increase to better investment
opportunities alone. Decisions: 104 financial/risk exclusions, 68 pattern/other,
42 specialist, 80 financial evidence unverified, 74 filing review, and 17
insufficient valuation evidence. These are first decision outcomes and may
hide additional failing criteria. The 51 old-baseline price alerts are not
new recommendations.

## Five shadow observations

Only twelve candidates were examined by the daily shadow budget: five
observations and seven nonmatches; 373 were deferred. This is not a full
fundamental review of all 385 names or a demonstrated success-rate sample.

| Name | Core outcome | Interpretation |
| --- | --- | --- |
| MYRG | Filing review | Review new credit terms, acquired business and cash conversion. |
| NET | Solvency exclusions | Current GAAP earnings and leverage fail the configured policy; shadow growth does not override them. |
| NOW | Persistent prior decline | Already on a separate disclosure watch; shape exclusion is not a finding that the business is insolvent. |
| NPO | Insufficient valuation upside | Improving operations do not by themselves support the target return. |
| NTAP | Risk score 4/10 | A heuristic exclusion, not a 40% failure probability. Saved valuation sensitivities also fail. |

NTAP's saved generic bull sensitivity is approximately -2.4%, below the
configured +50% objective. Removing its risk-score exclusion alone would not
create a qualifying case. No risk threshold is changed here.

## MYRG: promising operating evidence, incomplete investment case

The October 28 release reports $3.68bn backlog and $650.5m available under
the new $690m revolver. Availability is conditional credit, not cash. The
September 10 filing covers new financing. November 4's 8-K is tagged
Regulation FD (7.01/9.01); its full body was unavailable in this review.
Metadata alone must not be interpreted as a newly reported financial quarter.

The September 10-Q reports nine-month operating cash of $134.155m versus
$211.737m, capital spending of about $82m and $324.8m acquisition spending.
Higher profit did not translate into higher operating cash. Covenant limits
include maximum net leverage 3.0 and minimum interest coverage 3.0; reported
compliance does not supply a fully stressed headroom calculation.

The saved cap is $3.839bn and buffered TTM cash proxy $131.272m. A mechanical
50% return with 5% dilution at 20x equity cash would require about $302.35m
annual cash, 2.30 times that proxy. The multiple is illustrative, not justified
by peer evidence. Acquisition integration, contract working capital, five-year
funding, valuation and a sourced catalyst remain unresolved. Hold retained.

Sources:
- [Quarter filing](https://www.sec.gov/Archives/edgar/data/700923/000070092326000052/myrg-20260930.htm)
- [Credit event](https://www.sec.gov/Archives/edgar/data/700923/000070092326000047/myrg-20260908.htm)
- [October 28 results](https://investor.myrgroup.com/news-releases/news-release-details/myr-group-inc-announces-third-quarter-and-first-nine-months-2026)

## NPO: better business results, valuation remains the obstacle

Enpro reports Q3 sales growth of 22.4%, or 16.9% excluding acquisitions and
FX, and nine-month free cash of $129.2m, including capitalized software in
capital spending. Debt was $520.7m and cash $83.4m. Its adjusted EBITDA
leverage differs from the scanner's provider-based definitions; neither is
an independently verified covenant stress result.

At the saved $5.447bn cap, the same illustrative return/dilution/20x
sensitivity requires about $428.94m annual cash versus the saved buffered
TTM proxy of $141.7m, roughly three times as much. This comparison is not
a forecast or fair-value target. A materially different supported growth or
valuation case is needed; the generic watch gate remains unmet.

Source: [November 3 issuer results](https://www.enpro.com/for-investors/investor-news/news-details/2026/Enpro-Reports-Third-Quarter-2026-Results-Raises-Full-Year-Guidance/default.aspx).

## Next useful work

ASBIS report detection now works and its funding/cash-conversion hold remains.
Albemarle's preferred conversion and cycle review also remain open. TTD and
Sanmina have existing November 9 disclosure checkpoints. Their new financial
evidence, followed by focused underwriting of viable leads, is more useful
than relaxing filters to produce picks. A 50% return and five-year survival
have not been established for any new observation.

This review changes research documentation only. The production code and
financial selection thresholds are unchanged; no new runtime tests are needed.
