# Financial evidence and valuation model

## Scope

This model screens ordinary operating companies. All thresholds are conservative, configurable research choices; none are statistically calibrated bankruptcy probabilities, fair-value estimates or one-year forecasts. Banks/insurers/REITs go to specialist review rather than receive exemptions that imply safety.

## Recent decline and one-year recovery objective

The default discovery screen now requires a meaningful decline in the latest 63 trading intervals, rather than admitting old year-long drawdowns because prices remain low. It accepts a 20% drop across 21 intervals or from a peak in that 63-interval window, bounded by 100 calendar days. Dated price histories must have a current observation within seven calendar days; missing rows, duplicate dates and sparse suspended histories cannot manufacture recentness.

Generic FCF sensitivities identify research watches. They do not substantiate the one-year objective. `recovery_cases.py` separately checks reviewed, sourced company-specific assumptions, a measurable catalyst/invalidation condition and a future target date within 365 days. Positive current OCF, FCF and EBIT, covered hard solvency checks, current official publication/event checks and documented reviews of the five survival/listing topics are required. Records must match current financial periods and the latest periodic filing accession and expire after 30 days. Source dates cannot follow the recorded review date. See RECOVERY_CASES.md for the schema and its limits.

For discovery, reverse sensitivities calculate the cash flow or multiple needed to double. At unchanged normalized cash flow, the required equity FCF multiple is `2 × current USD market cap × (1 + generic assumed dilution) / normalized USD FCF`. At a specified multiple, required equity FCF is that same required equity value divided by the multiple. This is arithmetic about assumptions, not a forecast or a minimum/maximum-loss bound.

`DOCUMENTED_12M_CASE` means the reviewed research record meets the schema and conditional valuation thresholds. It does not authenticate document contents, guarantee a business outcome, or replace independent investment judgment. The actual registry starts empty; placeholders and fictional test cases are not investment candidates. New paper snapshots retain the goal status and source-record fingerprint; historical snapshots are never retroactively upgraded.

## Dated evidence

`fundamental_analysis.py` reads quarterly and annual balance sheets, cash-flow statements and income statements through yfinance. It records observation time, statement period ends, source row labels and fetch failures. These are provider statement dates, not verified publication dates. Do not use them retrospectively to claim a point-in-time historical backtest.

The latest available balance sheet is used without silently substituting older row values. Flow metrics use four distinct consecutive quarters, with quarter gaps of 60–120 days. A complete annual period is an explicit fallback; partial quarters are never annualized or mixed with annual amounts. Annual fallback is available up to 450 days for diagnostics; normal eligibility still requires each statement's latest period end within 200 days, and the balance/income/cash-flow dates aligned within 120 days. These choices will leave some international issuers unverified when Yahoo lacks interim data.

Missing debt, cash, interest, capex and equity are not zero. Explicit zero total debt establishes zero current debt; an absent total-debt row does not. NaN, infinity, future-dated statements and missing rows do not establish financial strength.

## Solvency calculations

Amounts in this section use the financial-statement currency, consistently across numerator and denominator.

- Debt/equity: total statement debt / positive book equity, maximum 2.5x. Non-positive equity with debt is excluded.
- Interest coverage: EBIT / absolute gross interest expense, minimum 2.5x. Operating income is a labeled fallback for EBIT. Missing/zero usable interest with debt leaves the company unverified. Net interest income is not substituted for gross expense.
- Net leverage: (total debt − cash equivalents) / positive EBITDA, maximum 3x for net-debt companies. Missing positive EBITDA for that assessment is unverified.
- Current-debt coverage: (cash + 75% of positive annual cash-flow proxy after the interest buffer) / current debt, minimum 1.25x. Current-debt line items can include leases and do not establish every contractual maturity.
- Cash runway: cash / annual cash burn × 12, minimum 24 months when burning cash. This assumes constant burn, unrestricted cash and no refinancing; it is a screening stress, not a forecast.
- Current assets/current liabilities, non-positive operating earnings, non-positive operating cash flow and annual share-count changes add review context. Share-count changes may include corporate actions; they are not automatically proven economic dilution.

CFO classifications differ across standards. The raw proxy is operating cash flow less absolute capex. For funding coverage and valuation, the model subtracts an **additional gross-interest buffer**, even where interest may already be included in CFO. This deliberately sacrifices comparability/precision for conservatism; it is not a standardized FCFE calculation. Debt with unavailable gross interest does not get a financing-adjusted valuation.

A critical exclusion wins over missing data. Missing required evidence wins over a favorable score. Technical bottom/RSI signals cannot undo either gate. Legacy quote-summary leverage is no longer an early admission authority; risk/report inputs are refreshed from the same dated statements used by the new checks.

## Contractual debt and specialist gaps

`Current Debt` is only a proxy for short-term obligations. The model does not extract complete maturities in months 13–24, covenants, acceleration provisions, cash restrictions, refinancing terms, guarantees, auditor qualifications or committed credit facilities. Indebted issuers with otherwise covered checks remain REVIEW/WATCH until a human reviews the latest filings. They are not represented as fully verified.

Bank review needs regulatory capital (including applicable CET1/capital requirements), funding/deposit stability, liquidity and asset quality. Insurance review needs jurisdiction-specific regulatory solvency, reserves, underwriting and asset/liability matching. REIT review needs issuer-reconciled FFO/AFFO, property and debt schedules, distribution coverage and maintenance capex. Do not apply generic thresholds without the relevant jurisdiction and business model.

Primary background: [FDIC regulatory capital](https://www.fdic.gov/capital-markets/regulatory-capital), [FDIC liquidity and funds management](https://www.fdic.gov/capital-markets/liquidity-and-funds-management), and [Nareit FFO definition](https://www.reit.com/glossary/funds-operation-ffo).

## Valuation sensitivity

Require positive current cash-flow proxy and at least three consecutive positive annual periods, approximately a year apart. Normalize using the **lower** of current TTM/annual proxy and the median of the required annual history, then subtract the additional current gross-interest buffer. Convert that amount to USD using financialCurrency FX. No valuation is supplied when the resulting amount is non-positive or evidence is incomplete/stale.

Defaults:

| Case | Cash-flow factor | Equity cash-flow multiple |
|---|---:|---:|
| Bear | 0.65 | 10x |
| Base | 1.00 | 15x |
| Bull | 1.20 | 20x |

For every case:

`scenario price = current quote price × (normalized USD cash flow × factor × multiple) / (current USD market cap × 1.05)`

The 1.05 factor is an illustrative 5% dilution assumption, not a forecast of issuance. Cash flow is an equity proxy after the financing buffer, so net debt is **not** subtracted again as it would be from an enterprise-value multiple. These multiples are not measured peers and the factors are not company forecasts. The model does not establish that any scenario will occur within twelve months or provide numerical probabilities. Bear/base/bull are assumption cases, not confidence intervals.

The shortlist currently requires base return >=20% and bull return >=100%, alongside the financial and existing qualitative/technical gates. A bull-2x flag is merely arithmetic under those assumptions. Case prices retain quote units, so GBp/ILA and major currencies produce the same percentage return after conversion.

## Inspect and reproduce

`research_report.json` includes evidence, missing fields, flags and scenarios even when a candidate fails admission. The Markdown report is a readable index. The full policy and its fingerprint are saved with evidence and paper selections. Change policy assumptions in `research_policy.json`; compare policy versions separately.

Validated with synthetic missing-data/period/currency regressions, production integration tests and small read-only live checks. The seven-listing validation run used `--no-email --no-paper` and produced no selections: three candidates failed persistent-decline shape checks and one failed financial checks. This is software validation, not an evaluation of investment performance.

## Next data required for investment-grade review

For any candidate with REVIEW or UNVERIFIED, obtain the latest issuer/regulator filing and identify the actual debt schedule through 24 months, covenant headroom, facility availability, cash restrictions and going-concern/auditor language. A source should include issuer, filing URL, publication date, statement currency and relevant page/note. For specialist sectors, obtain the regulatory and operating metrics listed above. Do not bypass unknowns by assigning convenient numbers or lowering thresholds to force picks.

A dated, sourced catalyst and defensible company/peer assumptions are also necessary before evaluating an investment. Live paper observations need time; missing delisting proceeds and absent historical point-in-time fundamentals still prevent claims of a validated strategy edge.

## Public sources without a paid subscription

`filing_review.md` is generated automatically for shortlisted, unverified, specialist-review and valuation-unverified candidates. It provides source starting points and the outstanding questions; rejected names are not promoted just because links exist. Search using the issuer name and confirm that the filing covers the listed parent, relevant period and reporting jurisdiction. A cross-listing does not establish the home regulator.

Public source references: [SEC EDGAR search](https://www.sec.gov/search-filings), [FCA National Storage Mechanism](https://www.fca.org.uk/markets/primary-markets/regulatory-disclosures/national-storage-mechanism), [Companies House public information](https://www.gov.uk/get-information-about-a-company), [TASE MAYA financial statements](https://maya.tase.co.il/en/reports/financial-report), [KNF issuer-information directory](https://www.knf.gov.pl/dla_konsumenta/kampanie_informacyjne/zrodla_informacji_o_emitentach), and [German Company Register](https://www.unternehmensregister.de/en). Some German deposited documents may carry a fee; an issuer's own investor-relations reports are a public alternative to investigate. The scanner's bounded SEC collector downloads permitted issuer/accession HTML and indexes topics for review; it does not infer missing legal terms or clear risks from keyword matches. It does not buy documents or register accounts. Other jurisdictions still require issuer/regulator document review.

The checklist covers identity/current filings, maturities, covenant headroom, unrestricted liquidity, going-concern/auditor language, missing gross-interest evidence and a sourced recovery catalyst. Record URL, filing publication date, period, note/page, units and unresolved questions. Finding a link is not verification, and completing a checkbox alone does not change admission status.
