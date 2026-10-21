# Fallen Angel Scanner: investment logic and code review

Reviewed 21 October 2026 against commit `3ac0ef5e1dd9c46f5531329725cdedc68129ee48`.
Repository: https://github.com/tshprung/fallen-angel-scanner

## Assessment

This is a useful research shortlist generator, but I would not use its existing BUY NOW labels to allocate money. It identifies sharp price declines and applies several sensible exclusions; it does not establish intrinsic value, a temporary cause, a probability of doubling, or a probability of surviving. A low internal score is not a calibrated estimate of bankruptcy risk.

Your goal is best expressed as: financially resilient businesses with a defensible recovery thesis and a plausible 100% upside scenario over roughly twelve months. No public equity screen can ensure zero bankruptcy, delisting, or capital-loss risk. Business survival also does not prevent a 50% stock-price loss. The SEC investor education discussion is useful context: https://www.investor.gov/introduction-investing/investing-basics/investment-products/stocks

## What is already useful

- Multiple markets, market-cap floors, liquidity filters, biotech exclusions, and a two-stage process.
- Leverage, cash flow, profitability and Piotroski checks; distinction between sudden declines and prolonged deterioration.
- Company-specific news filtering and an explicit unknown-cause state.
- Email reporting and persisted monitoring state.

## Material findings

1. **International screening uses inconsistent currencies — unresolved.** In `stage1_quick_filter`, `info.marketCap` is compared directly against USD floors. `passes_avg_dollar_liquidity` multiplies local prices by volume and compares with USD thresholds. GBP/GBp and ILS/ILA quote units require separate treatment. `market_cap_usd` subsequently contains that same unconverted value. Debt and cash must also be reconciled with `financialCurrency` before comparing with market cap. Fix with cached, timestamped FX conversion and explicit quote units; missing FX should cause an unverified/watch status. Add cross-market and cross-financial-currency regressions before enabling international ranking.

2. **Historical prices are mistaken for value — partially fixed.** `estimate_recovery_target` calls a price average historical P/E but never uses the P/E or EPS variables. It discarded estimates below 130% of the current price and could invent a 50% upside fallback without usable history. This creates optimistic selection bias. The patch keeps contrary estimates, removes the invented fallback, and labels results as recovery references. Historical prices and analyst consensus still do not prove fair value, and analyst freshness is not established.

3. **Split adjustment is applied twice — fixed.** The enhanced runner manually divides prior OHLC values by every split despite Yahoo history ordinarily being split adjusted. This can distort declines, chart shape and recovery references. The patch delegates error detection to yfinance `repair=True` and preserves already adjusted prices. Official upstream description: https://github.com/ranaroussi/yfinance/blob/main/doc/source/advanced/price_repair.rst . Provider repair is not a guarantee of clean data.

4. **A haircut can increase displayed upside — fixed.** `estimate_recovery_target_with_valuation_sanity` previously switched from midpoint upside to upper-bound upside after a haircut. Example: a 180–220 range at price 100 has 100% midpoint upside; after an 85% haircut it becomes 168–202, but previously reported 102% upside. It now reports 85%, consistently applying the haircut to the reference midpoint. Bounds describe dispersion, not probabilities.

5. **The initial screen is too narrow for your broader thesis — unresolved.** Stage 1 requires at least a 20% decline over approximately 21 trading days. It misses names down substantially over six to twelve months that have since stabilized. Add separate recent-shock and sustained-drawdown cohorts. Keep timing signals separate from business quality so an oversold indicator cannot substitute for evidence of value.

6. **Report confidence exceeds the evidence — improved.** Unknown catalyst records can retain `at_bottom=True` and previously render BUY NOW. The enhanced overlay also maps raw risk 4 to 3, while report headings assert low bankruptcy risk. The patch renders unknown/elevated-risk names WATCH, shows raw risk, changes bottom signals to RESEARCH, and removes blanket low-bankruptcy claims. Risk compression remains in admission/ranking and should be removed in a subsequent policy change.

7. **Survival checks have missing-data holes — unresolved.** Missing leverage may receive a neutral 0.5 D/E; absent interest and cash-flow data can bypass checks. The authoritative guard refreshes D/E but net debt remains based on quote-summary values. A current ratio alone does not assess refinancing needs. Add data coverage, statement dates, cash runway, interest coverage from statements, debt due within 12–24 months, and dilution. Missing evidence should mean UNVERIFIED, not financially safe. Banks, insurers and REITs need dedicated models; exempting them from operating-company debt checks does not validate their safety.

8. **Headlines cannot demonstrate a temporary problem — unresolved.** Keyword classifiers can mistake a durable earnings decline for an overreaction or a denial of fraud for evidence of fraud. Require a sourced event date, link, business impact, measurable resolution condition and time window. An earnings miss is an event, not proof of recovery.

9. **No validated one-year edge — unresolved.** The scanner's 50% main recovery threshold and 20% fresh-crash threshold are neither a doubling forecast nor empirical probabilities. There is no demonstrated out-of-sample 12-month performance evaluation in the reviewed code. Current index membership and current fundamentals cannot honestly be used as historical inputs.

## Recommended next version

Use sequential evidence gates rather than a single score that lets good technicals offset weak solvency:

1. Eligible market, USD-normalized size, tradable liquidity and verified data coverage.
2. Sector-appropriate solvency, cash generation and refinancing analysis.
3. Business quality: multi-year profitability, cash conversion, competitive position and dilution.
4. Valuation: explicit bear/base/bull scenarios using normalized earnings or free cash flow, sector-appropriate multiples, net debt and diluted shares. Every scenario must show assumptions and sources. Multiples must match the earnings metric.
5. Recovery catalyst: what changes, what evidence would confirm it and why that could happen within twelve months.
6. Entry timing and portfolio concentration assessed separately from underlying value.

For each candidate display bear/base/bull prices and returns, a 2x scenario flag, financial-data age, unresolved risks, catalyst deadline and thesis-invalidation condition. A bull-case 2x flag is not a 2x probability. Do not invent numeric probabilities until a relevant out-of-sample cohort supports them. Do not force a fixed number of picks when evidence is weak.

Validate with point-in-time statements and universes including delisted failures, next-session entries, transaction costs and FX. Measure the 12-month 2x hit rate, median return, maximum drawdown, major-loss rate and benchmark excess return. Distinguish touching 2x during the year from ending the year at 2x. Forward paper tracking can start now, but historical price-only simulations cannot validate a fundamental strategy using today's financial information.

## Delivered changes and validation

The patch changes recovery references, split handling, raw-risk display and action labels. It deliberately does not claim to implement the unresolved financial model or FX work above.

Offline verification: 50 tests passed, including 13 new regression cases; syntax compilation passed for all production modules. No live market scan, email, GitHub push, or investment transaction was performed. Tested with local Python 3.14; the repository workflow uses Python 3.10, which was not executed here. These checks validate code behavior, not investment performance.

## Apply the patch

From a clean checkout at the reviewed commit:

```sh
git apply --check scanner-improvements.patch
git apply scanner-improvements.patch
python -m pip install -r requirements.txt pytest
python -m pytest tests test_email_generation.py test_fresh_crash_bucket.py -q --import-mode=importlib -p no:cacheprovider
```

The explicit test paths and importlib mode avoid the repository's existing duplicate test filenames. Inspect the patch before deploying. Production is `scanner_entry.py`; the README currently documents the base runner and needs a broader rewrite. Running production with email environment variables can send notifications.
