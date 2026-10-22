# Deferred-candidate review and funding follow-up

Reviewed October 22, 2026. This is incremental research, not a completed recovery case or a buy recommendation. Existing selections, paper observations and historical artifacts were not rewritten.

## All 48 filing-held records received preliminary economic triage

The [completed scan](https://github.com/tshprung/fallen-angel-scanner/actions/runs/39736578913) had 48 candidates held for filing review. Using their saved financial evidence and separately timestamped public capitalization/FX observations:

- 20 lack the positive current/annual FCF history required by the existing generic model.
- One, DY, has no positive normalized cash flow after the additional interest buffer.
- The other 27 have a positive normalization, but every observed market capitalization exceeds the maximum supporting both configured base and bull upside thresholds under those assumptions.
- Quote/FX retrieval succeeded for all 27 assessed capitalizations. This does not verify the underlying statements, current events or cause of the decline.

The accompanying `2026-10-22-deferred-triage.json` retains all 48 held records, observation times, currency conversion, model gaps and the calculation. No held company received an investment target or selection. The capitalization ceiling is an algebraic screening benchmark, not fair value. Stale financial evidence or unreviewed transactions may materially change the result.

| Closest preliminary arithmetic comparisons | Observed market cap / model ceiling |
|---|---:|
| PNR | 1.24x |
| IBP | 1.80x |
| SKY | 1.97x |
| BIRK | 2.09x |
| KAI | 2.36x |
| STRL | 2.78x |
| EXTR | 3.20x |
| CW | 3.62x |

A ratio above one fails the configured arithmetic. It does not establish a necessary price decline or a forecast; growth, normalization, dilution and multiples are assumptions requiring company-specific work. This triage is a way to allocate further research, not a finding that none of the companies can recover.

## Pentair: a plausible operating recovery, with a changed funding picture

At the original scan observation of USD 52.86, PNR was 24.4% below its recent closing peak. It is the closest of these 48 under the preliminary generic comparison, but remains held.

Pentair's [July 14 warning](https://investors.pentair.com/news-releases/news-release-details/pentair-announces-chief-financial-officer-transition-and) identifies Pool-channel destocking and worse business conditions. It estimated a full-year USD 250m sales impact and USD 155m segment-income impact from destocking, and cut adjusted EPS guidance to USD 4.60–4.80 from USD 5.30–5.40. The company described preparing channel inventory for the 2027 pool season. That is a sourced recovery hypothesis, not proof the adjustment ends or demand returns within a year. CFO turnover also occurred; the release does not establish misconduct.

The [July 28 acquisition announcement](https://investors.pentair.com/news-releases/news-release-details/pentair-acquire-taco-group-holdings-accelerating-growth-and) expected Taco to add USD 0.10–0.15 to adjusted FY2027 EPS. Run-rate synergies and tax benefits were included in its transaction economics; do not count them a second time or assume immediate cash realization. The [October 1 closing announcement](https://investors.pentair.com/news-releases/news-release-details/pentair-completes-acquisition-taco-group-holdings) confirms the roughly USD 1.4bn acquisition completed after the June balance-sheet period used in the scan.

The [September 2 financing filing](https://www.sec.gov/Archives/edgar/data/77360/000110465926104725/tm2624576d1_8k.htm) describes USD 400m maturing 18 months after closing and USD 1bn due May 5, 2030. A first-tranche draw at the October 1 close would point to April 2028, inside the 24-month horizon. Actual post-close draws, refinancing and contractual covenant headroom need reconciliation; pre-acquisition provider ratios are insufficient. The detailed terms remain in the sourced hold registry.

Therefore PNR now has a sourced PENDING hold that persists until actual acquisition funding, cash, maturities, covenant headroom and combined-company cash flow are reconciled. A September-period balance sheet would itself still predate the October close. The [October 27 scheduled earnings report](https://investors.pentair.com/) may provide further disclosures, but a reporting date is not a guaranteed recovery catalyst.

Doubling USD 52.86 means USD 105.72 before dividends. At illustrative 15x or 20x future diluted earnings, this requires EPS of USD 7.048 or USD 5.286. The higher-multiple route is numerically closer to dated guidance, but neither that multiple nor the needed earnings has been established. The generic normalization would need roughly 24% more cash flow at its unchanged assumptions merely to reach the binding upside benchmark; current source reconciliation remains necessary.

## ASBIS: the annual report supplies a baseline, not current funding clearance

The [signed 2025 audited financial statements](https://investor.asbis.com/download/cache/Asbis_Annual_FS_2025_SIGNED.pdf) are scanned pages: an empty text extraction is not evidence of missing disclosures. Relevant original pages were rendered and inspected.

The auditor opinion on printed page 6 is unmodified for the 2025 statements. It does not establish current solvency. Note 35 on printed pages 74–75 supplies contractual liability buckets at December 31, 2025, explicitly including principal cash flows only. The group table has USD 1,042.117m due within three months and USD 70.995m in months 3–12, mainly operational trade payables and short-term financing. Do not label the entire total bank debt or treat routine working-capital turnover as an immediate unfinanced cash shortfall. The 1–2 year bucket totals USD 16.786m, including bank loans and leases. These old buckets do not cover the full October 2026–October 2028 horizon or prove that facilities were renewed on unchanged terms.

Note 20, printed page 56, reports full financial/non-financial covenant compliance throughout 2025 and at year end, with no breaches or defaults during that year. This dated issuer assertion does not establish current headroom. Current lender commitments, renewal/borrowing-base conditions, numeric covenant thresholds/headroom and post-June collections remain unresolved. No ASBIS funding or listing clearance was entered.

## Preventing repeated deferral

Previously the bounded collector could revisit the same routine issuers every day while the tail stayed deferred. After selections, qualifying near misses and sourced holds, available routine slots now advance by a full batch each UTC day through a ticker-sorted queue. With an unchanged queue and available slots, subsequent runs cover later names. Repeated runs on one day remain stable; changing membership or priority demand can change coverage. The per-run budget and all admission/hold rules remain unchanged. Tests verify full-batch coverage, stable ordering, budget enforcement and preservation of exclusions.
