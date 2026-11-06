# Documenting a conditional recovery case: up to two years

The objective is a recent price decline, a financially resilient business with durable customer value, and a defensible path to at least +50% within one year or +100% when the case takes more than one year and at most two years. A +50% six-month case also qualifies. These are user-defined acceptable outcomes, not equal annualized returns. A low price or generic bull sensitivity alone does not meet this objective.

`recovery_cases.json` is a reviewed-research registry, initially empty. Do not create an issuer record until the relevant source contents have actually been examined. A URL is provenance, not proof that its contents support an assumption. The evaluator validates completeness, freshness, input alignment and arithmetic; it does not authenticate a researcher's conclusions or assign return/survival probabilities.

The current official-filing prerequisite supports US SEC issuers only. Non-US candidates can appear as research watches, but cannot receive a documented-case status until equivalent official-source validation is implemented. Scanning five listing markets does not imply five-market filing clearance.

Each source-backed block needs a nonempty `finding` and at least one `sources` object with an HTTPS `url` and `published_at`. Identify the document section/page in the finding, explain units, and distinguish reported numbers from forward assumptions. Cite official filings or issuer releases where available. A peer multiple needs a dated peer comparison; a financial report by itself does not justify an arbitrary multiple. Do not enter unknown amounts as zero.

For each ticker, record:

- `reviewed_at`: date of the substantive review. It must be no more than 30 days old under the default policy.
- `statement_periods`: exact current provider `balance`, `cashflow` and `income` period ends.
- `filing_accession`: exact accession of the latest periodic filing returned by the official checker. New statements or a new periodic filing invalidate alignment.
- `cause`: a source-backed explanation of the recent decline. Identify the actual event rather than labeling all guidance cuts temporary.
- `historical_reference`: a source-backed higher historical price within five years, with `price`, matching quote `currency`, `observed_on` no later than the review date, `price_basis: split_adjusted_comparable_business`, and a nonempty `comparability` explanation. Review splits, spin-offs, acquisitions, dilution and changes in the business. An earlier price is context, not proof of fair value; the recovery scenario may differ from it.
- `catalyst`: a source-backed explanation with `expected_by`, `metric` and `invalidation`. The milestone must be ahead, within 730 days and on/before the valuation date. State why its resolution could change earnings/cash generation or the valuation.
- `target_by`: a future date after/on the catalyst, no more than 730 days from the scan. Targets within 183 days use `DOCUMENTED_6M_CASE`, within 184-365 days `DOCUMENTED_12M_CASE`, and within 366-730 days `DOCUMENTED_24M_CASE`. Longer cases require at least +100%, including day 366; a +50% two-year scenario does not qualify. This is a conditional valuation date, not a promised result.
- `risk_reviews`: the six source-backed topics below. Use `REVIEWED_NO_UNRESOLVED_CONCERN` only after actually checking the contents and documenting the analysis. Any other status keeps the candidate a watch.
- `business_reviews`: all five source-backed topics listed below. Each requires `status: SUPPORTED_WITH_IDENTIFIED_RISKS`, `finding`, `sources`, and nonempty `risks` describing adverse evidence and uncertainties. Survival alone cannot substitute for these reviews. Missing or unresolved topics block documented status; headlines and product announcements are not proof of a competitive advantage.
- `monitoring`: a sourced block with `next_review_by` (future, no more than 90 days ahead and on/before target), a measurable `metric`, and an `invalidation` condition. A checkpoint reaching its date without a refreshed substantive review blocks documented status. Do not keep extending a target solely because the share price failed to recover.
- `opportunity_cost`: a sourced block with `benchmark` and `reassessment_rule`. Explain why the prospective reward justifies the time and risk, and what missing operating progress would trigger reassessment. Compare benchmark and stock over the same dates; do not automatically sell solely because the benchmark rose faster. The declared comparator is research, not an automatically fetched forecast. Paper tracking currently supports only SPY for USD observations; other comparisons require manual work.
- `valuation`: source-backed company-specific assumptions using `basis: equity_fcf_usd_after_financing`, `expected_dilution_fraction` and `cases` for `bear`, `base` and `recovery`. Each case needs its own source-backed finding plus positive `equity_fcf_usd` and `equity_fcf_multiple`. Explain how cash flow includes financing costs and maintenance/capitalized development spending. Do not subtract net debt a second time from an equity cash-flow value. Translate currencies explicitly. Scenario values must be ordered; the base must meet policy's minimum upside (+20%) and recovery must meet the applicable +50%/+100% hurdle after dilution. A recovery scenario is an upside scenario, not a most-likely outcome or calibrated probability.

Required risk-review topics:

| Field | What to establish from current documents |
|---|---|
| `liquidity_and_maturities_24m` | Actual contractual repayments for 24 months, unrestricted cash, facility availability/expiry, stressed cash needs and funding headroom. |
| `covenants` | Thresholds, current headroom, waivers and triggers that could accelerate repayment. |
| `going_concern` | Auditor opinion, management liquidity statements, subsequent events and funding dependencies. |
| `listing_and_corporate_actions` | Listing compliance, minimum-price notices, proposed delisting, merger/tender terms and whether the ticker will continue. |
| `dilution` | Convertible settlement, capped calls, share issuance, stock compensation and repurchases relevant to the modeled share base. |
| `resilience_5y` | Contractual maturities and funding through five years, stressed cash generation and investment needs, refinancing dependencies, structural competitive risk and contingent obligations. Distinguish cash from conditional facilities and liquid investments. Explain adverse paths, not just today's ratios. This review is not a five-year survival guarantee. |

Required business-review topics:

| Field | What to establish from current sources |
|---|---|
| `customer_need` | Why customers still need the service and why they pay this company; distinguish logo retention from spending, renewals, cancellations and budgets. |
| `competitive_position` | Alternatives, relative outcomes, market-share evidence, switching costs and access to suppliers/distribution. Name credible competitors. |
| `technology_relevance` | Substitution, AI, regulation and changing workflows. Identify what might make the product unnecessary or commoditized. Product announcements do not demonstrate customer adoption or superior economics. |
| `pricing_power_and_unit_economics` | Fees, gross/operating margins, customer economics, cash after investment, stock compensation and dilution. A useful product can still earn an inadequate return for shareholders. |
| `structural_decline` | Evidence distinguishing a reversible setback from lasting erosion. Include counterevidence, the conditions that invalidate the recovery thesis and the business's plausible state in two years. |

These fields enforce explicit reviewed evidence, not automated verification of a moat. The evaluator checks schema, dates, provenance and arithmetic; an actual issuer assessment still requires reading and interpreting documents. The registry remains empty until such work is completed.

The target calculation is `current quote price × scenario equity value USD / (current market cap USD × (1 + expected dilution))`, where equity value is the scenario's after-financing equity cash-flow proxy times its supported multiple. Returns exclude dividends, taxes and trading costs. Show total and annualized returns over the actual dated horizon; annualization is a comparison, not a promise that returns can repeat. The generic reverse sensitivities for 183/365/730 days use their own explicitly labeled dilution assumption and do not establish that the valuation can be reached by those dates. The 24-month minimum uses `minimum_24m_upside_pct`; shorter cases use `minimum_bull_upside_pct`. The generic sensitivity remains a +50% watch screen, not a time-specific forecast.

Unresolved bankruptcy, listing, liquidity or transaction concerns must remain unresolved even if the valuation looks attractive. A reviewed narrative cannot override hard financial exclusions, unavailable official-source checks, stale financial periods or an old price decline. An unresolved merger that would retire the ticker belongs in separate transaction research.

The source registry should not contain test examples or placeholder companies. Tests use fictional data separately. Leave the real registry empty when no completed case is supported; the daily email will report research watches and the remaining work in `recovery_review.md`.
