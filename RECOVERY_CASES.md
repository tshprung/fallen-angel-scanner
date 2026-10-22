# Documenting a conditional twelve-month recovery case

The objective is a recent price decline, a business financially resilient enough to withstand it, and a defensible path to roughly 2x within one year. A low price or generic bull sensitivity alone does not meet this objective.

`recovery_cases.json` is a reviewed-research registry, initially empty. Do not create an issuer record until the relevant source contents have actually been examined. A URL is provenance, not proof that its contents support an assumption. The evaluator validates completeness, freshness, input alignment and arithmetic; it does not authenticate a researcher's conclusions or assign return/survival probabilities.

The current official-filing prerequisite supports US SEC issuers only. Non-US candidates can appear as research watches, but cannot receive `DOCUMENTED_12M_CASE` until equivalent official-source validation is implemented. Scanning five listing markets does not imply five-market filing clearance.

Each source-backed block needs a nonempty `finding` and at least one `sources` object with an HTTPS `url` and `published_at`. Identify the document section/page in the finding, explain units, and distinguish reported numbers from forward assumptions. Cite official filings or issuer releases where available. A peer multiple needs a dated peer comparison; a financial report by itself does not justify an arbitrary multiple. Do not enter unknown amounts as zero.

For each ticker, record:

- `reviewed_at`: date of the substantive review. It must be no more than 30 days old under the default policy.
- `statement_periods`: exact current provider `balance`, `cashflow` and `income` period ends.
- `filing_accession`: exact accession of the latest periodic filing returned by the official checker. New statements or a new periodic filing invalidate alignment.
- `cause`: a source-backed explanation of the recent decline. Identify the actual event rather than labeling all guidance cuts temporary.
- `catalyst`: a source-backed explanation with `expected_by`, `metric` and `invalidation`. The milestone must be future-dated within 365 days. State why its resolution could change earnings/cash generation or the valuation.
- `target_by`: a future date after/on the catalyst, no more than 365 days from the scan. This is the case's valuation horizon, not a promised result.
- `risk_reviews`: the five source-backed topics below. Use `REVIEWED_NO_UNRESOLVED_CONCERN` only after actually checking the contents and documenting the analysis. Any other status keeps the candidate a watch.
- `valuation`: source-backed company-specific assumptions using `basis: equity_fcf_usd_after_financing`, `expected_dilution_fraction` and `cases` for `bear`, `base` and `recovery`. Each case needs its own source-backed finding plus positive `equity_fcf_usd` and `equity_fcf_multiple`. Explain how cash flow includes financing costs and maintenance/capitalized development spending. Do not subtract net debt a second time from an equity cash-flow value. Translate currencies explicitly. Scenario values must be ordered; the base must meet policy's minimum upside and recovery must support at least +100% after dilution.

Required risk-review topics:

| Field | What to establish from current documents |
|---|---|
| `liquidity_and_maturities_24m` | Actual contractual repayments for 24 months, unrestricted cash, facility availability/expiry, stressed cash needs and funding headroom. |
| `covenants` | Thresholds, current headroom, waivers and triggers that could accelerate repayment. |
| `going_concern` | Auditor opinion, management liquidity statements, subsequent events and funding dependencies. |
| `listing_and_corporate_actions` | Listing compliance, minimum-price notices, proposed delisting, merger/tender terms and whether the ticker will continue. |
| `dilution` | Convertible settlement, capped calls, share issuance, stock compensation and repurchases relevant to the modeled share base. |

The target calculation is `current quote price × scenario equity value USD / (current market cap USD × (1 + expected dilution))`, where equity value is the scenario's after-financing equity cash-flow proxy times its supported multiple. Returns exclude dividends, taxes and trading costs. The generic reverse sensitivity uses its own explicitly labeled dilution assumption and does not become the company's forecast.

Unresolved bankruptcy, listing, liquidity or transaction concerns must remain unresolved even if the valuation looks attractive. A reviewed narrative cannot override hard financial exclusions, unavailable official-source checks, stale financial periods or an old price decline. An unresolved merger that would retire the ticker belongs in separate transaction research.

The source registry should not contain test examples or placeholder companies. Tests use fictional data separately. Leave the real registry empty when no completed case is supported; the daily email will report research watches and the remaining work in `recovery_review.md`.
