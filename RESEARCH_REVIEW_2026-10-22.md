# Universe research review — 22 October 2026

The completed [research-only Actions run](https://github.com/tshprung/fallen-angel-scanner/actions/runs/39736578913) tested commit `3e4dc0c0a545a9517e58972c0be10314365a5b05`. It sent no email and created no paper selections. Download the run's `research-only-39736578913` artifact for the complete evidence and individual decisions. Observations are dated scan inputs, not executable prices.

## Coverage and result

| Measure | Result |
|---|---:|
| Configured symbols processed | 1,699 / 1,699 |
| Successful quote responses | 1,698 |
| Price histories checked | 1,588 |
| Recent-decline candidates | 384 |
| Recorded price/currency/history gaps | 19 |
| Company-analysis exceptions | 0 / 384 |
| Research selections | 0 |
| Documented conditional 12-month recovery cases | 0 |

Provider health remains DEGRADED because 13 symbols had unverified currency and six had insufficient history. The combined no-recent-decline/price-unverified outcome and missing-volume outcomes also need individual interpretation. This configured universe does not cover every stock or market. Missing evidence is not an investment rejection.

| Candidate decision | Count |
|---|---:|
| Financial exclusion | 102 |
| Not selected, persistent pre-drop decline | 86 |
| Specialist review | 70 |
| Unverified financial evidence | 56 |
| Filing review | 48 |
| Insufficient generic value upside | 8 |
| Heuristic risk exclusion | 7 |
| Valuation unverified | 4 |
| Sourced event hold | 3 |

The bounded filing collector attached document indexes for 12 issuers: three complete within the requested document scope and nine partial. Another 39 eligible issuers were deferred by its budget. An indexed document does not clear a risk, and collection completion does not mean every candidate received a filing-content review. The three existing event holds remained active. News-source access also remained imperfect; for example, LZB returned no company-specific headlines, so no cause was inferred.

## Closest numerical lead: La-Z-Boy (LZB)

At the scan's observed USD 28.68 price, LZB was 31.9% below its recent peak. Covered provider financial checks had no hard exclusion flags. Its generic sensitivity was bear USD 15.72 (-45.2%), base USD 36.28 (+26.5%), bull USD 58.04 (+102.4%). These are configurable, uncalibrated cash-flow/multiple assumptions, not price targets or a one-year forecast. The heuristic risk score was 4/10 against an admission requirement below four, so **LZB was not selected**. No threshold was relaxed.

The [latest 10-Q](https://www.sec.gov/Archives/edgar/data/57131/000005713126000035/lzb-20260725.htm), for July 25, reports USD 89.354m current and USD 452.157m long-term lease liabilities. Their sum exactly matches the provider's USD 541.511m total-debt proxy; treating that entire field as bank borrowing would be misleading. The USD 200m revolver matures July 1, 2030. No borrowings were outstanding and the issuer reported covenant compliance at quarter end; this does not establish current covenant headroom or full undrawn availability. Quarterly OCF USD 15.648m less capex USD 23.284m gives negative USD 7.636m FCF. Provider period labels use July 31 rather than the filing's July 25 and need explicit reconciliation before a documented case.

The [issuer results release](https://ir.la-z-boy.com/2026-08-18-La-Z-Boy-Incorporated-Reports-First-Quarter-Results-Retail-Momentum-With-Positive-Written-Same-Store-Sales) reports USD 267m cash, no external debt, retail written same-store sales growth of 3%, consolidated sales down 3%, GAAP EPS -0.06 and adjusted EPS 0.43. Retail momentum is a research hypothesis, not an established explanation of the decline or proof of recovery within a year.

Outstanding: source the actual decline, reconcile the latest financial periods and lease/funding schedule, verify covenant thresholds and headroom, assess subsequent events, listing and dilution, and build company-specific recovery assumptions with measurable milestones and invalidation conditions. No completed recovery record was created.

## Other leads and exclusions

- **ASBIS (ASB.WA):** observed PLN 152.50, 21.0% below its recent peak. Covered financial checks require further review, while generic normalized cash flow fails the upside screen. Strong preliminary September sales in the [October 20 issuer report](https://investor.asbis.com/news/current-reports/current-report-24-2026) do not establish sustainable profit or cash conversion. Funding, working capital, factoring and the cause of the decline remain unresolved. No selection or recovery record was created.
- **MGM:** its generic sensitivity passes the arithmetic upside test, but leverage, interest coverage and missing current-debt evidence prevent admission. A high illustrative return cannot override those exclusions; lease accounting also needs company-specific interpretation.
- **Stride (LRN):** remains on its sourced event hold. The [September-quarter filing](https://d18rn0p25nwr6d.cloudfront.net/CIK-0001157408/1d1a2d21-a0d6-4164-b728-a643ec91008e.html) requires review of USD 420m convertible principal due September 1, 2027 and potential conversion dilution. Current note terms were added to the review registry without clearing it.

## Software validation and next research

The quote-reuse/outage changes passed 220 automated tests, the GitHub Python matrix and live SEC probes. An earlier nominally successful run had 370/384 company-analysis failures after provider authentication errors; it is an outage example, not evidence of no opportunities. The final run above has zero such exceptions. Within-run quote reuse avoids redundant quote requests; majority source failures now preserve the audit and abort email/paper output.

GitHub Actions is sufficient for this workload. The main remaining work is issuer-specific evidence, sustainable cash-flow and recovery assumptions, and accumulating prospective paper outcomes. These checks cannot establish zero bankruptcy/delisting risk or guarantee a doubling. Non-US documented-case support and historical point-in-time/delisting data remain limitations; paying for a server would not resolve them.
