# November 5 email and disclosure review

Reviewed the email received November 5 at 01:14 Warsaw and the corresponding
saved scan. No recovery case is admitted and no trades are recommended.

## Source coverage

The run used 7b5434f and saved state as 49e4241. It processed all 1,699 symbols,
loaded 1,698 verified-currency quotes, examined 277 price candidates and
recorded 141 gaps, down from 455. The prior widespread quote authentication
problem was not reproduced: maximum consecutive quote failures was one.

However, 132 gaps occurred after a successful quote during currency/security
checks, one at the quote stage and eight at price-history sufficiency. All
four configured non-US markets were blocked by common FX failures. Calling
the source coverage restored would therefore be incorrect.

[Run logs](https://github.com/tshprung/fallen-angel-scanner/actions/runs/41937041337/job/126948007795)
show non-US processing after 00:03 UTC on November 5, but the global FX checker
was constructed before midnight on November 4. Its frozen process-start
timestamp rejected the new day's rate as future-dated. The same problem
affected CAD conversion for ALM, the single company-analysis error. This
explains why the previous daytime production probe passed while overnight
coverage did not recover.

Live FX checks now refresh the validation clock both when called and after
retrieval, including requests that themselves cross midnight. Explicit
historical/test as-of dates remain fixed. Future/stale/nonpositive/missing
rates and contradictory candles remain blocked; the latest-daily-candle
request and bounded retry are retained. No dates or prices are relabeled.

A November 5 live check through scanner_entry successfully retrieved dated
EUR, GBP, PLN, ILS and CAD observations. This validates the adapters in a
limited probe, not the next full GitHub scan. Midnight-boundary tests cover
both a scan crossing midnight and a request crossing midnight, together with
fixed historical time and continued future/stale rejection.

## ASBIS: newly published September statements

The signed September statements are now linked by the issuer; last night's
watch predated their availability. Q3 revenue was $2,186.738m and parent profit
$51.779m, but operating cash flow was negative $46.396m. Nine-month operating
cash was $30.940m; subtracting PPE $12.367m and intangibles $13.032m leaves
$5.541m before financing distributions. Q3 receivables and inventory absorbed
$268.786m and $116.617m, partly funded by $300.446m additional trade payables.
This is growth-related funding pressure, not proof of insolvency.

Cash at bank was $272.692m, including $25.882m pledged. Short-term borrowings
were $270.075m, including overdrafts, loans, leases and factoring; a separate
$51.270m supplier-factoring liability must not disappear from funding review.
Facility ceilings are not automatically unrestricted cash or verified committed
headroom. Collections, funding terms, covenant headroom and a five-year stress
remain unresolved. Added a manual hold and updated the existing disclosure
question; a refreshed provider snapshot cannot clear these issues.

Source: [Signed interim statements, September 30](https://investor.asbis.com/download/ASBIS_FS_Q3__9M_2026_signed.pdf).
Cash-flow pages 4-5 and borrowing note 17 were rendered and visually checked.

## Albemarle: improved results do not clear the hold

The November 4 release reports Q3 operating cash of $406m and free cash flow
$325m, supported by a Talison dividend. Reported liquidity of $3.4bn includes
$1.8bn cash and facilities, not $3.4bn cash. Q4 Energy Storage sales and
adjusted EBITDA are expected to decline sequentially with lower market prices
and higher-cost inventory. Added this evidence to the existing hold; preferred
conversion, normalized JV cash, lithium-price stress and five-year funding
still require completion. The new September 10-Q was detected, but its full
body could not be independently retrieved in this review.

Source: [Issuer November 4 release](https://www.albemarle.com/us/en/news/albemarle-reports-third-quarter-2026-results).

## Three new shadow observations

KLAC and LRCX pass the exploratory growth/cash screen but fail the core
valuation sensitivities. KLIC remains held for fiscal-date and event review.
These are observations, not investment cases. At saved market caps, a purely
mechanical 50% upside with 5% dilution and a 20x equity-cash-flow multiple
would require annual cash flow of approximately $15.37bn, $21.82bn and $282m
for KLAC, LRCX and KLIC respectively, versus saved buffered proxies of
$3.76bn, $6.39bn and $39.8m. The multiple is illustrative, not peer-derived;
these comparisons neither establish fair value nor predict returns. New
growth alone does not justify overriding the valuation requirement.

Priority: establish full non-US coverage on the next scan, review ASBIS funding
and collections, and complete ALB's conversion/cycle work. The November 9
TTD and Sanmina disclosure checkpoints remain configured. No paid data
purchase or server deployment is needed for the changes in this review.
