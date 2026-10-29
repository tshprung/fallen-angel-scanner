# Economic triage of the filing-review backlog

Reviewed October 29, 2026. Research priorities only; no selections, cleared holds, investment targets or forecasts.

## Coverage and method

The [October 28 daily run](https://github.com/tshprung/fallen-angel-scanner/actions/runs/40782451212) had 42 filing-review records and one sourced event hold. All 43 received preliminary triage:

- 15 lack the positive current/annual FCF evidence required by the generic normalization.
- DY has no positive normalization after the additional interest buffer.
- SFD's manual hold has no saved financial evidence in this audit, so it cannot be ranked by this calculation.
- The other 26 normalize positively. All 26 observed capitalizations exceed the generic upside ceiling; none passes that arithmetic. All required quote/FX requests succeeded.

The saved statements remain unreconciled research inputs. Capitalizations and FX were observed separately on October 29; this is not a replay at October 28 prices. The adjacent `2026-10-29-backlog-triage.json` retains source-report SHA-256, timestamps, statement periods, saved policy, normalization inputs and source gaps. Its matching report was generated October 28 at 23:08:24 UTC. No historical report or paper entry was overwritten.

For each positive normalization, the ceiling is the smaller of:

`normalized FCF × scenario FCF factor × equity FCF multiple / ((1 + dilution) × (1 + required upside))`

The model uses the saved policy's base and bull scenarios. Dividing observed capitalization by this ceiling identifies the size of the arithmetic gap. A value above one does not establish fair value or prove recovery impossible; it indicates how much the assumptions need company-specific justification. It does not predict a price decline. Filing clearance alone would still leave risk, valuation, catalyst and source-reconciliation requirements.

| Research order under this preliminary comparison | Market cap / generic ceiling |
|---|---:|
| SFM | 1.43x |
| BIRK | 2.07x |
| KAI | 2.37x |
| STRL | 2.62x |
| EXTR | 3.47x |
| CW | 3.50x |
| ODFL | 3.54x |
| NFLX | 3.72x |

## SFM: closest arithmetic, but weaker fresh evidence

The [October 28 release](https://investors.sprouts.com/news/news-details/2026/Sprouts-Farmers-Market-Inc--Reports-Third-Quarter-2026-Results/default.aspx) reports comparable sales down 0.9%, cites consumer weakness and cyclospora disruption, and guides Q4 comparable sales down 2–4%. Its 52-week EPS guidance is approximately USD 4.80. Reported cash is USD 228.664m and revolver drawings are zero; this does not remove substantial lease and other finance obligations.

Using statement-table gross PP&E purchases, nine-month OCF less investment is USD 270.917m versus USD 401.390m: down 32.5%. Combined with the [2025 annual release](https://investors.sprouts.com/news/news-details/2026/Sprouts-Farmers-Market-Inc--Reports-Fourth-Quarter-and-Full-Year-2025-Results/), the rolling proxy is USD 337.258m. This is before a newly verified gross-interest buffer. It does not improve on the saved model's cash-flow input. Gross investment must not be mixed with the highlighted net-of-landlord-reimbursement figure.

At the saved October 28 price of USD 62, doubling requires USD 124: EPS of USD 6.20 at an assumed 20x multiple, or 25.83x the current-year guide. Neither is established. Next verify traffic recovery, disruption duration, lease maturities and sustainable returns on new stores. Separate growth investment from maintenance using evidence, without adding spending back while also assuming its full growth benefit. No admission.

## BIRK: growth merits research, but funding and valuation remain conditional

The [August 13 issuer release](https://www.birkenstock-holding.com/news/birkenstock-reports-fiscal-third-quarter-2026-results-with-15percent-constant-fx-revenue-growth-led-by/ea946937-0de8-419e-b169-012ebbc89b2f) reports 15% constant-currency quarterly sales growth and 19% adjusted EPS growth. Guidance is EUR 1.90–2.05 adjusted EPS for FY2026. A EUR 230m buyback and EUR 900m note issuance changed financing; higher cash must not be treated as purely operating cash generation. Reported June net leverage was 1.8x on the issuer's adjusted basis, not a current covenant-headroom measure.

At the saved USD 31.59 price and separately observed USD/EUR 1.112966, doubling would require approximately 27.7–29.9x that guidance, or EUR 2.84 EPS at 20x. These are reverse sensitivities, not peer-supported multiples or earnings forecasts. FY2026 guidance is not an estimate for October 2027 earnings.

Next reconcile refinancing terms, maturities, lease treatment, covenant definitions and tariff/FX exposure; assess whether earnings growth supports a recovery case without an unsupported multiple expansion. Provider debt categories and official lease/borrowing categories require reconciliation. Do not use reported EBITDA leverage as a substitute for complete funding clearance. No admission.

## KAI: operating progress, with a larger valuation hurdle

The [August 4 issuer release](https://investor.kadant.com/news-releases/news-release-details/kadant-reports-second-quarter-2026-results) reports 23% sales growth, including 13 percentage points from acquisitions and 8 points organically; gross margin declined 210 basis points. FY2026 adjusted EPS guidance is USD 12.43–12.68, excluding acquisition-related costs.

At the saved USD 265.80 price, doubling would require about 42.3x the guidance midpoint if earnings were unchanged. Acquisition growth, integration expenses and cyclical capital-project timing need separate analysis. The provider's June 30 period labels also require matching to the issuer's July 4 fiscal period. Next reconcile the financing/payment calendar and a sourced forward earnings bridge before assigning a recovery multiple. A strong quarter is insufficient to establish the required one-year upside. No admission.

## Next research decision

Prioritize SFM for reconciliation of newly published statements and BIRK for a company-specific earnings/funding review. KAI's larger arithmetic gap lowers its priority within this small comparison; it is not a short thesis. Future evidence may change this order. The generic model is deliberately conservative and uncalibrated; passing or failing it does not estimate doubling or bankruptcy probabilities.

`2026-10-29-backlog-sensitivities.json` records fiscal periods, source URLs and reverse-sensitivity arithmetic. The dated quote observations are not executable prices. Direct local issuer downloads were blocked; cited releases were reviewed through web retrieval, not saved as verified local source-body archives. No scanner thresholds, filing resolutions, manual holds, active recovery cases or paper entries were changed.
