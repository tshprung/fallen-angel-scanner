# Fallen Angel Scanner

A research scanner for listed equities in the US, UK, Germany, Poland and Israel. Its goal is to find companies whose shares fell recently, whose finances can withstand the setback, and whose sourced recovery case could support doubling within about a year. Research watches are explicitly distinguished from documented conditional twelve-month cases. It does not predict returns or guarantee survival or continued listing.

## Run

```sh
python -m pip install -r requirements.txt pytest
python -m pytest tests test_email_generation.py test_fresh_crash_bucket.py -q --import-mode=importlib -p no:cacheprovider
python scanner_entry.py
```

`scanner_entry.py` is the production entry point. With `SENDER_EMAIL`, `RECEIVER_EMAIL` and `SENDER_PASSWORD` configured it sends email. The scheduled workflow runs on weekdays at 18:30 UTC (20:30 Warsaw during summer time, 19:30 during winter time).

For a small validation run without email or additions to the paper ledger:

```sh
python scanner_entry.py --tickers TTD,LULU,AZN.L --no-email --no-paper --output-dir validation
```

These tickers illustrate software use; they are not recommendations. `--no-email` by itself still records genuine selections to paper tracking. `--no-paper` disables those additions. `--output-dir` directs reports and run-state files to that directory. Imports and `--help` do not download index universes. The CLI handles UTF-8 output on Windows.

## Selection process

1. **Eligible security:** configured USD market-cap and liquidity floors; listed equities; biotech exclusions retained.
2. **Recent price decline:** at least a 20% fall across exactly 21 price intervals or from a peak within the latest 63 trading intervals, roughly three trading months. Dated peaks must also be within 100 calendar days; the latest price cannot be over seven calendar days old. Old declines without a new qualifying fall no longer enter by default. Missing rows are not dropped to manufacture a recent window. The persistent-decline shape exclusion remains.
3. **Financial evidence:** current balance sheet, operating cash flow, capex, earnings, interest and debt. Four consecutive quarters form TTM data; annual fallback is explicitly labeled. Missing figures stay missing.
4. **Solvency:** statement debt/equity, interest coverage, net leverage, cash burn and stressed coverage of current debt. Hard financial exclusions cannot be offset by favorable technicals. A raw risk score of 4 is no longer compressed to 3.
5. **Research watches:** positive current cash flow and at least three consecutive positive annual cash-flow periods. Generic base sensitivity of at least +20% and bull sensitivity of at least +100% identifies a watch for further work. It does not establish a one-year doubling thesis. Reverse sensitivities show the equity cash flow or multiple that doubling would require.
6. **Documented twelve-month case:** requires current sourced research on the cause, a measurable catalyst, an invalidation condition, and company-specific bear/base/recovery valuations including dilution. The catalyst and target must lie ahead within 365 days. Covered solvency gates, positive current operating earnings/cash flow, current SEC publication checks, and reviewed liquidity/debt, covenants, going concern and listing/corporate-action concerns are mandatory. Records expire after 30 days and must match current statement periods and the exact latest filing accession. A documented case can pass its own valuation thresholds even if the generic sensitivity does not. It remains conditional research, not a recommendation or calibrated probability.

The main shortlist uses fundamental scenarios, rather than treating a return to a past share price as fair value. Historical recovery helpers remain for compatibility but do not determine the new shortlist. Report-size limits prioritize documented cases and then use fixed financial criteria. They never loosen assumptions to fill a report. Headlines mentioning earnings, guidance or a downgrade cannot establish a recovery catalyst by themselves.

`recovery_cases.json` initially contains no issuer claims. [RECOVERY_CASES.md](RECOVERY_CASES.md) defines how reviewed research is recorded; it is not automatically filled with invented forecasts. US SEC metadata checks are live, but reading and reconciling source contents still requires research. Non-US listings can remain research watches while their local sources are unresolved; they cannot become documented cases through absent SEC coverage.

Each run produces `recovery_review.md` with the specific missing evidence and doubling requirements for selected watches. Email subjects report documented cases and research watches separately. `research_report.json` preserves both ticker lists and case details. New paper observations store the research-case status and fingerprint as they were at selection; earlier observations remain unchanged. This policy revision creates a new financial-policy fingerprint and must not be pooled with older cohorts as if selection rules were unchanged.

## Reports and review queues

Each completed run writes `research_report.md` and `research_report.json`, including exclusions, missing evidence, statement period ends, source row labels, scenario inputs and a policy fingerprint. The daily workflow preserves and commits these alongside paper observations. It also uploads artifacts before attempting the state commit.

- `EXCLUDE`: at least one covered financial check breached policy.
- `UNVERIFIED`: required evidence is missing, stale, inconsistent or unusable. It cannot enter the ordinary-company shortlist.
- `SPECIALIST_REVIEW`: a bank, insurer, REIT, other financial business or real-estate company needs a different model. Ordinary-company ratios do not qualify it for the shortlist.
- `REVIEW`: covered checks did not breach policy, but known questions remain. For indebted companies this includes debt due in months 13–24, covenants and committed facilities. Shortlisted names with this status display WATCH.
- `SCREEN_PASS`: only the covered checks passed. This does not verify all risks or establish investment suitability.

No paid data subscription is required to continue. Each run also produces `filing_review.md`: a focused queue with issuer website/public filing links and the exact evidence still needed. US candidates link to SEC EDGAR; UK candidates to FCA/Companies House; Israeli candidates to MAYA; Polish candidates to KNF's official source directory; German candidates to the Company Register (some deposited documents may carry fees; issuer investor-relations reports are another starting point). Routes follow the listing market, so confirm issuer identity and reporting jurisdiction. These links are starting points and do not automatically verify or upgrade a financial status.

An empty shortlist is valid. Price-decline alerts are watch prompts, not instructions to average down. Their financial thesis must be reassessed. Legacy non-USD price baselines without verified quote units are skipped rather than compared across ambiguous units.

`review_holds.json` records sourced manual findings that block ordinary-company selection with decision `event_review`, before deduplication or provider requests. The research audit and filing queue retain the reason, dated sources and release condition. Holds do not expire automatically: resolve them only with recorded evidence after the condition is met. This is a small manually maintained registry, not a comprehensive corporate-action or latest-publication feed. No record does not mean no event. Existing paper snapshots remain historical observations and are not rewritten by a later hold.

## Automated official filing checks

US candidates that pass the financial-evidence gates are checked against the SEC ticker/exchange mapping and submissions API before selection. The checker confirms ticker/CIK identity, compares all three provider statement period ends with the latest periodic filing, and flags covered current-report items, merger forms and financial-report amendments. New results/outlook disclosures after the latest periodic filing require review, even when a provider news feed is empty. This detects publication metadata; it does not read or interpret the filing bodies or attached earnings releases.

- `METADATA_CHECKED`: the covered metadata checks found no unresolved flag. It does not verify financial amounts, covenant terms, debt maturities, guidance or a recovery thesis.
- `REVIEW_REQUIRED` / decision `filing_review`: newer statements or covered events need reconciliation; the company is held out of selection and its valuation target is suppressed.
- `UNVERIFIED` / decision `filing_unverified`: access, identity, schema or coverage could not be established. The company is held out of selection. HTTP 403 and missing mappings never become empty successful searches.
- `NOT_COVERED`: supported non-US listing suffixes continue through the existing financial screen with WATCH review labeling and local-regulator links. They do not receive a verified SEC status.

Coverage is limited to merger forms in the last 365 days and specified 8-K/6-K items in the last 180 days. Older unresolved situations, guidance only on an issuer website, and events not identifiable from filing metadata can still be missed. Read `sec_filings.py` for the exact forms/items. The manual holds remain necessary and never clear automatically. Known event flags can be resolved in `sec_filing_reviews.json` only for an exact `10-digit CIK:accession` key, with `reviewed_at`, `source_url` matching that filing, and a substantive `finding`. A new accession or amendment requires a new review. Resolving an event cannot bypass stale statement dates or unavailable SEC access.

Every checked candidate retains dated sources and findings in the JSON/Markdown report and filing queue; selected paper snapshots retain the filing check as observed at selection. Emails show filing holds even when no stocks qualify. These added selection rules distinguish new observations from earlier cohorts even if their financial-policy fingerprint is unchanged.

The daily GitHub Actions job restores a public-response cache. Submissions expire after 15 minutes and ticker mappings after seven days; expired cache is never used as clearance when a source is unavailable. Requests are sequential, throttled below two per second and bounded by timeouts/retries. Optional repository variable `SEC_USER_AGENT` overrides the application identity; otherwise the daily scan uses its configured sender address as SEC contact identification. The address is sent to the SEC in the HTTP User-Agent, never printed in reports. Outside the workflow, `SEC_CONTACT_EMAIL` can supply contact identification; without it the public repository URL identifies the application. No paid API key is required. See the [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and [fair-access guidance](https://www.sec.gov/about/developer-resources).

Pushes to main also run a separate live SEC access health check on GitHub's runner, alongside offline tests. Its artifact records access status for LCII/LRN/SFD; it sends no email and changes no scanner or paper state. A failed health check is visible in Actions and must not be interpreted as a passed integration. Local access can differ from runner access. To probe manually:

```sh
python sec_filings.py --probe-output sec_source_probe.json
```

## Financial model and policy

### Filing contents and research findings

The daily run now fetches bounded filing bodies for final selections and filing/event holds, including the latest periodic report, an available annual report and recent current reports. It can follow one same-issuer, same-accession HTML exhibit. The default limit is 12 issuers, three primary documents plus one exhibit each, with a 12 MiB limit per document. Selections are processed first, then risk-score near misses that have covered financial checks and pass the generic upside screen, then sourced review holds, then other eligible cases. This research priority never changes admission, risk scores or holds; hard financial failures do not enter the near-miss queue. Deferred work and unavailable sources remain explicit. Downloads share SEC throttling and contact identification. Decoded public filing bodies are cached privately under `.sec-cache` for up to seven days; amendments use new accession URLs. Headers/contact details are never cached or published.

`filing_contents.md` and the JSON audit provide source URLs, retrieval times, decoded-content fingerprints and paragraph/table block locations for liquidity, debt, covenants, going concern, listing/transactions, dilution and outlook. Hidden inline-XBRL data and scripts/styles are excluded. Extracted amount/date tokens retain raw context; they are not a complete repayment calendar, normalized financial statement or legal interpretation. Negations, conditional clauses and ordinary risk boilerplate are not classified as actual defaults. This index never clears a hold or upgrades a recovery case. The live Actions probe verifies the latest primary filing body for each of LCII/LRN/SFD; its deliberate document-budget deferrals are visible.

After priority cases, remaining filing-review slots rotate through a ticker-sorted routine queue by a full batch each UTC day. Repeated runs on the same day use the same order. With an unchanged queue and available slots, this prevents the first issuers from repeatedly consuming the budget while later names remain deferred. Priority cases still come first and can consume all slots; deferral never implies clearance.

Manual source-backed `review_notes` in `review_holds.json` appear in the filing queue and review email, while the hold remains pending. Notes must cite a matching dated source in that record. This separates incremental research findings, including possible financing improvements, from a completed recovery thesis.

[research_policy.json](research_policy.json) holds the research thresholds and valuation assumptions. [FUNDAMENTALS.md](FUNDAMENTALS.md) explains calculations, source coverage and limitations. The original [review](SCANNER_REVIEW.md) is retained as historical context.

Statement amounts use `financialCurrency`; price amounts use quote metadata. Size, liquidity, cash/market-cap and net-debt/market-cap comparisons use USD. FX uses a timestamped valid Yahoo observation no older than seven calendar days and is cached for the run. Missing/unsupported currencies and unavailable FX skip the candidate.

GBp/GBX and ILA quote units are explicitly reconciled, including repair-mode changes to major currency units. Minor-unit market cap is checked against shares outstanding and the quote price. Cash/debt in the report are USD; share prices remain in quote units. Liquidity uses the scan's FX rate, rather than a historical daily-FX average. Supported major currencies: USD, GBP, EUR, PLN, ILS, CHF, CAD, AUD and JPY.

## Forward paper tracking

Final selections are appended to `paper_tracking.json` independently of email delivery. A ticker/day snapshot is immutable and stores financial evidence, policy, solvency status and valuation assumptions. Re-running the same day does not rewrite it. The scheduled workflow refreshes observations and commits the ledger and [readable report](paper_tracking_report.md).

```sh
python paper_tracking.py
```

The hypothetical entry is the first session after the UTC selection date, at its adjusted open. Only sessions before the refresh date are used, avoiding incomplete bars. The twelve-month exit is the first session on or after 365 calendar days from entry. Interim marks use the latest close. Returns are split/dividend adjusted in the listing currency, before costs, taxes and slippage. This is forward observation, not a portfolio simulation; USD returns and benchmark excess returns are not yet computed.

The ledger distinguishes reaching 2x at a daily close from ending twelve months at 2x. Failed histories remain unverified; stale prices and large data gaps are flagged. This retains possibly delisted names but does not supply missing delisting proceeds, so it cannot yet establish an unbiased success rate. Daily observations of the same stock are correlated; policy versions must not be pooled as if they were one unchanged strategy.

Tracking begins when a successful scheduled scan selects candidates. There are no backfilled picks or claimed investment results.

Paper performance method v2 rejects duplicate session dates, unusable closes, contradictory supplied OHLC bounds and gaps over ten calendar days within the holding window. It does not infer every exchange trading session or supply missing delisting proceeds. An entry and a year-end quote alone cannot establish a completed outcome. Previously completed observations without the current method version are rechecked on the next refresh; selection snapshots remain unchanged. Completed observations assessed under the current method stay frozen.

The daily refresh also writes `paper_tracking_summary.json` and a cohort table in `paper_tracking_report.md`. These separate the financial policy, price-screen cohort and research status recorded at selection; missing legacy labels remain explicit. Each cohort shows observation and unique-ticker counts, pending/tracking/unverified counts, completed observations, touches of 2x, twelve-month exits at 2x and exits below entry. Only completed observations under the current performance method contribute to those outcome counts. Repeated ticker/day cohorts are correlated, unresolved outcomes are retained, and neither these counts nor a small sample establishes a success probability, a bankruptcy rate or a delisting rate. Policy labels do not capture every change to code, sources or manual holds; inspect recorded evidence before combining observations for research. Benchmark excess returns and USD returns remain future work.

## Validation and remaining work

For an independent research run, open **Actions → Research-only universe scan → Run workflow**. Leave `tickers` empty for the configured universe, or enter a comma-separated subset. This workflow uploads its reports without sending email, appending paper selections or committing scanner state. The initial addition of this workflow also runs it once on main.

`scan_coverage.json` checkpoints the requested symbols, processed count, outcome counts and source gaps every 25 symbols. A stopped run retains `completed: false`. Completed research reports include these coverage counts. Configured or fallback index lists are not the whole market; missing quotes, currency verification and insufficient history are data gaps, not evidence that a company failed the investment criteria. Some price/liquidity outcomes combine a screen rejection with unusable price/volume evidence and are labeled accordingly.

Quote/ticker objects are reused between stages only within one run, with observation times retained in the company audit. They are cleared on success or failure and never carried into another run. This avoids redundant Yahoo quote requests after a large universe scan. An incomplete quote without a currency is a source failure, not a zero-valued company. `scan_scope.provider_health` exposes price-source gaps and company-analysis exceptions. If at least half of ten or more price observations or company analyses fail on those covered source/error checks, the run preserves its report and fails before email or new paper entries. This is an operational outage threshold, not a financial rule; lower error counts and missing statement evidence remain visible and do not establish full coverage. Completed financial analysis is checkpointed before optional filing-content collection.

Offline regressions cover currencies, corporate actions, data gaps, period alignment, solvency gates, valuation arithmetic, production integration and paper tracking. Push/PR CI tests Python 3.10 and 3.12 without sending email. SciPy is required by yfinance repair mode and is declared in requirements.

Remaining investment-research work: interpreting filing contents/covenants and 13–24 month maturities, broader event/publication coverage, sector/jurisdiction-specific financial models, sourced recovery catalysts, defensible peer multiples, and empirical validation. Yahoo statement data does not establish an issuer's going-concern assessment, restricted-cash availability or complete debt obligations. See FUNDAMENTALS.md before treating any output as investable.

Price-history repair is not proof of correctness. When full OHLC bars are present, the history adapter rejects contradictory bounds (for example, a repaired close below the day's low) as a source error rather than dropping rows, clamping prices or manufacturing a decline. Consistent bars can still be wrong; this check does not replace independent price verification.

## Independent disclosure follow-up

The existing daily Actions run also checks `disclosure_watchlist.json`, initially PNR, ASB.WA and LZB. These checks run before stock screening, including for held companies and names outside the price screen. SEC checks compare the latest periodic filing and covered current reports; ASBIS checks its issuer financial-report index for the configured quarter. ASBIS links require manual content review and do not establish regulatory coverage. Expected dates are research checkpoints, not guaranteed publication times; LZB has no confirmed next date configured.

`disclosure_watch.json` and `disclosure_watch.md` record source times, documents, new links and unresolved questions. `disclosure_watch_state.json` retains comparison history between successful daily runs. A first observation establishes a baseline; subsequent new documents, an already-listed expected report on first observation, or the first overdue checkpoint can trigger the normal report email even with no candidates. The first overdue checkpoint means the target report was not confirmed by this checker, not that the issuer failed to report. Source failures remain explicitly `UNVERIFIED`; previous metadata is never presented as current clearance. They appear in artifacts and any otherwise-generated daily email, but do not independently trigger email. This is a daily check, not immediate or guaranteed notification delivery.

New disclosures never clear holds, approve financial evidence, change valuations or create paper selections. Review the linked documents and reconcile the question before changing a research case. The existing scan's provider-outage guard can still prevent email; Actions preserves the disclosure artifacts. No additional server, schedule or paid API is required.

For a standalone check without scanning, sending mail or changing the paper ledger:

```sh
python disclosure_watch.py --output-dir disclosure-output
```

To include it in a research-only scan, add `--watch-disclosures --no-email --no-paper` to `scanner_entry.py`. Push CI preserves a separate live disclosure probe alongside the SEC access results; unavailable sources are recorded in its JSON, rather than treated as successful financial verification.
