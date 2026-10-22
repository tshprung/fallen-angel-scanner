# Fallen Angel Scanner

A research scanner for listed equities in the US, UK, Germany, Poland and Israel. It looks for recent shocks or older drawdowns that have stabilized, checks dated financial evidence, and calculates transparent cash-flow sensitivities. It does not predict one-year returns or guarantee business survival.

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
2. **Price cohort:** at least a 20% fall across exactly 21 price intervals, or at least a 30% drawdown with the latest 21-session fall no worse than 15%. Older-drawdown screening requires at least 200 observations. The existing persistent-decline shape exclusion remains.
3. **Financial evidence:** current balance sheet, operating cash flow, capex, earnings, interest and debt. Four consecutive quarters form TTM data; annual fallback is explicitly labeled. Missing figures stay missing.
4. **Solvency:** statement debt/equity, interest coverage, net leverage, cash burn and stressed coverage of current debt. Hard financial exclusions cannot be offset by favorable technicals. A raw risk score of 4 is no longer compressed to 3.
5. **Value sensitivity:** positive current cash flow and at least three consecutive positive annual cash-flow periods. Cash flow is conservatively normalized and scenarios show every multiple, growth factor and dilution assumption. The main shortlist requires base sensitivity of at least +20% and bull sensitivity of at least +100%; these are configurable research cutoffs, not predicted returns.

The main shortlist uses these fundamental scenarios, rather than treating a return to a past share price as fair value. Historical recovery helpers remain for compatibility but do not determine the new shortlist. Report-size limits rank using fixed criteria rather than quietly tightening valuation thresholds to fill a report.

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

## Validation and remaining work

Offline regressions cover currencies, corporate actions, data gaps, period alignment, solvency gates, valuation arithmetic, production integration and paper tracking. Push/PR CI tests Python 3.10 and 3.12 without sending email. SciPy is required by yfinance repair mode and is declared in requirements.

Remaining investment-research work: interpreting filing contents/covenants and 13–24 month maturities, broader event/publication coverage, sector/jurisdiction-specific financial models, sourced recovery catalysts, defensible peer multiples, and empirical validation. Yahoo statement data does not establish an issuer's going-concern assessment, restricted-cash availability or complete debt obligations. See FUNDAMENTALS.md before treating any output as investable.
