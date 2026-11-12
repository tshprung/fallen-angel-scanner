# Point-in-time backtest

The offline runner compares a deterministic **scanner-core proxy** against drawdown-only, value/quality without drawdown, sector/size/liquidity matches, and a tradable market benchmark. It reuses the scanner's distribution-aware drawdown, solvency and valuation functions. It also checks archived SEC/hold status and excludes equity stubs. It does not reconstruct the live watchlist universe, headline/Piotroski/risk overlays, discretionary cases or AI. Results cannot establish live-strategy parity or five-year survival.

See the [data acquisition and acceptance checklist](BACKTEST_DATA_SOURCES.md) for provider coverage, a minimum export, and the public EDGAR accession audit.

## Run the synthetic smoke test

```sh
python backtest_demo.py demo-data
python backtest.py run --data demo-data/dataset.json --protocol demo-data/protocol.json --lock demo-data/lock.json --fold holdout --output-dir demo-report
```

The output must say `SYNTHETIC_ONLY`. Fictional crashes, recoveries and venue sessions are deliberately chosen to exercise the code. Their returns have no empirical meaning.

## Run the hosted development pilot

```sh
python build_quantconnect_pilot.py quantconnect-pilot
```

In a QuantConnect Python project, use **Explorer → Workspace → New File** to create `fa_pilot_inputs.py` and `fa_pilot_replay.py`. Paste the matching generated source into each file and save. The two files fit the [Free plan's per-file limit](https://www.quantconnect.com/docs/v2/cloud-platform/projects/files#07-Quotas). Create `fallen_angel_pilot.ipynb` in the same workspace and run this code cell with **Shift+Enter**. See [QuantConnect's research notebook guide](https://www.quantconnect.com/docs/v2/cloud-platform/research/getting-started).

```python
import json
from fa_pilot_replay import run_quantconnect_pilot
print(json.dumps(run_quantconnect_pilot(), indent=2))
```

The pilot uses QuantConnect's Research APIs and keeps market data in memory on the platform. The output contains aggregate coverage and order counts only.

The pilot uses a single June 2022 signal, three public filing cases, a 365-day horizon, and SPY. It exercises the shared ranking and execution code, the historical universe join, and Citrix's verified merger proceeds with an unknown payment date. For SPY it requires an exact match to the ex-date list in [State Street's U.S. distribution history](https://www.ssga.com/us/en/intermediary/resources/documents/etf-dividend-distributions). It uses the sponsor's amounts and the first regular session after the published payment date for cash availability. It reports feed amounts that disagree with the sponsor beyond ordinary cent rounding. The final SPY dividend remains a receivable at the end of the pilot window, and other stock payments remain unverified.

`DEVELOPMENT_ONLY` confirms that the wiring ran. This is a purpose-selected case set with one fully mapped financial snapshot. The reported performance gate remains `INSUFFICIENT_EVIDENCE`. A cloud-side API or data mismatch returns `INPUT_CHECK_FAILED` with the stage and exception type.

For the 32-stock June 2022 coverage audit, run the original sampler in its QuantConnect notebook. Paste [quantconnect_cohort.py](quantconnect_cohort.py) into a new cell in the same notebook. It reuses the installed pilot modules and requires a unique sample of 32 stable security IDs present at the dated cutoff, including the 15 previously audited names. If necessary, assign the original sampler's output of stable IDs or symbols to `cohort_ids` before running the audit. Do not regenerate a cohort based on which names had complete data or favorable results.

The coverage audit applies the existing raw price and liquidity floors, uses dated public share counts only when the issuer matches, and checks the shared distribution-aware drawdown rule. The three composite share reconstructions (Bowlero, EastGroup Properties and EchoStar) need additional basis checks before they can pass the verified market-cap gate. Tencent Music's [filing](https://www.sec.gov/Archives/edgar/data/1744676/000119312521111096/d31001d20f.htm) identifies the listed security as an ADS. Missing data, absent entry and horizon opens, delisting evidence, and payment dates are reported as counts in the full result from `run_cohort_audit`. A complete strategy comparison still requires fully mapped financial statements, time-stamped event clearance, verified corporate action coverage and broader dates.

The coverage audit matches regular stock dividends to public payment records using historical ticker, issuer CIK, ex-date and amount. It treats the first regular open after the stated payable date as the earliest simulated cash availability. Conflicting amounts leave the payment date unverified. The report includes unresolved dividends in the potential holding window, starting after the entry open's session and through the planned exit session. [Citrix September](https://www.sec.gov/Archives/edgar/data/877890/000119312521228138/d108726dex991.htm) · [Citrix December](https://www.sec.gov/Archives/edgar/data/877890/000119312521319281/d219736dex991.htm) · [Marten June](https://www.marten.com/press-release/marten-transport-announces-quarterly-dividend-and-an-increase-in-share-repurchase-program/) · [Marten December](https://investor.wedbush.com/wedbush/article/gnwcq-2022-11-30-marten-transport-declares-quarterly-dividend) · [Marten March](https://investor.wedbush.com/wedbush/article/gnwcq-2023-2-20-marten-transport-declares-quarterly-dividend)

The holding-window reference table also covers four payments each for Bank of America, Manulife, National Bank Holdings, Select Medical, Westamerica, and Xerox. Manulife uses its issuer-published gross USD rates before withholding. The June 2023 Xerox dividend went ex before the July 3 horizon and was payable July 31. [Bank of America September](https://investor.bankofamerica.com/regulatory-and-other-filings/select-sec-filings/content/0000070858-22-000112/bac-20220630.htm) · [Bank of America December](https://newsroom.bankofamerica.com/content/newsroom/press-releases/2022/10/bank-of-america-declares-fourth-quarter-2022-stock-dividends-.html) · [Bank of America March](https://newsroom.bankofamerica.com/content/newsroom/press-releases/2023/02/-bank-of-america-declares-first-quarter-2023-stock-dividends.html) · [Bank of America June](https://newsroom.bankofamerica.com/content/newsroom/press-releases/2023/04/-bank-of-america-declares-second-quarter-2023-stock-dividends.html) · [Manulife](https://www.manulife.com/ca/en/about-us/investors/dividends) · [National Bank Holdings](https://www.nationalbankholdings.com/stock-info/dividend-history/default.aspx) · [Select Medical FY2022](https://www.selectmedical.com/-/media/project/selectmedical/inpatients/selectmedical/page-assets/media-and-news/documents/2022-er/2022-annual-report-10-k.pdf) · [Select Medical FY2023](https://www.selectmedical.com/-/media/project/selectmedical/inpatients/selectmedical/files/media-and-news/2023-annual-report-10-k.pdf) · [Westamerica August](https://www.westamerica.com/westamerica-bancorporation-declares-quarterly-cash-dividend-and-announces-stock-repurchase-plan-4/) · [Westamerica November](https://www.westamerica.com/westamerica-bancorporation-declares-quarterly-cash-dividend-24/) · [Westamerica February](https://www.sec.gov/Archives/edgar/data/311094/000117184323000505/exh_991.htm) · [Westamerica May](https://www.westamerica.com/westamerica-bancorporation-declares-quarterly-cash-dividend-26/) · [Xerox](https://investors.xerox.com/node/19666) · [Historical ex-date rule](https://www.sec.gov/files/rules/sro/nasdaq/2023/34-98954.pdf)

`drawdown_financial_checks` reports one disposition for each verified drawdown signal. The audit applies the filing hold and specialist routing, uses negative trailing free cash flow to rule out Ameresco, Marten and Select Medical, checks Xerox against the existing consolidated net-debt-to-market-cap gate, and checks whether MSA Safety could meet the valuation thresholds even before the interest buffer and cash-flow normalization. Those partial checks can only rule a case out. Qualification requires the shared scanner-core financial checks with complete evidence. `drawdown_outcome_gaps` counts absent opens, unmatched delisting terms and unresolved cash dates for the same signals. [Ameresco filings](https://www.sec.gov/Archives/edgar/data/1488139/000148813922000072/amrc-20220331.htm) · [Marten filings](https://www.sec.gov/Archives/edgar/data/799167/000143774922011121/mrtn20220331_10q.htm) · [Select Medical filings](https://www.sec.gov/Archives/edgar/data/1320414/000162828022012695/sem-20220331.htm) · [Xerox filing](https://www.sec.gov/Archives/edgar/data/1770450/000177045022000020/xrx-20220331.htm) · [MSA quarterly filing](https://www.sec.gov/Archives/edgar/data/66570/000006657022000015/msa-20220331.htm) · [MSA annual filing](https://www.sec.gov/Archives/edgar/data/66570/000006657022000007/msa-20211231.htm)

The notebook prints the compact `cohort_replay` result. Once the verified drawdown signals have complete outcome inputs, the shared simulator runs the drawdown-only group and SPY on the same entry and exit sessions with default trading costs and participation limits. For this fixed holding period, the SPY replay uses the four USD cash distributions published by its US sponsor, including one payable after the exit. It reports missing, unexpected and duplicate feed dates and any amount differences. The report shows the percentage of initial capital used and counts the drawdowns that qualified for the scanner core. The June 2022 coverage run found three drawdowns and zero qualifications. All three drawdowns cleared the outcome checks after dividend reconciliation. One signal date and a small cohort leave the performance gate at `INSUFFICIENT_EVIDENCE`. [State Street US historical distributions](https://www.ssga.com/us/en/intermediary/resources/documents/etf-dividend-distributions)

## Run the multi-date development batch

Use the existing QuantConnect project with `fa_pilot_inputs.py` and `fa_pilot_replay.py`. Generate one notebook cell, paste its contents into a blank Python Research notebook in that project, and run it once. The cell prints the aggregate summary and leaves the detailed result in `batch_result` inside the notebook.

```sh
python build_quantconnect_pilot.py --batch-cell quantconnect-batch-cell.py
```

The frozen development schedule uses the last regular session of March and September from 2020 through 2023. The cell samples up to 16 issuers per date using a fixed hash of the date and stable security ID. The sample uses the dated vendor listing classification and size estimate before reading returns. It includes USD primary common shares with a CIK and a vendor market cap above the existing floor. Reported coverage reflects that sample. The 365-day replay uses the next regular open and the first regular open on or after the horizon. The holding windows can overlap and the date-level returns are separate experiments.

The batch reports a provisional drawdown-only replay using the vendor size screen when stock price inputs are complete. Unverified dividend payment dates, unresolved delisting notices on filled positions, and missing exit inputs suppress that portfolio's return. SPY uses the four sponsor distributions in each holding window. The cell also simulates a separate SPY trade using the capital deployed by each strategy and the same cost model. [State Street US distribution history](https://www.ssga.com/us/en/intermediary/resources/documents/etf-dividend-distributions)

For the scanner-core comparison, supply independently reconciled public evidence in `batch_verified_evidence` before running the cell. Its optional `facts` mapping uses `(signal date, ticker, CIK)` keys and the facts fields in the input contract below. Its optional `dividends` mapping uses `(ex-date ticker, CIK, ex-date)` keys and `(payable date, USD amount, source ID)` values. The batch reuses the previously reconciled June pilot dividends where dates and identity match. It checks statement availability and blocks the core comparison when required inputs are incomplete. Pending delistings remain visible as unresolved outcomes. The initial run identifies which evidence is missing and reports `DEVELOPMENT_BATCH_ONLY`.

## Freeze a real experiment

```sh
python backtest.py init-protocol protocol.json
# Set all three date ranges, sizing, cost and acceptance assumptions before evaluating.
python backtest.py freeze --data history.json --protocol protocol.json --lock experiment.lock.json
python backtest.py run --data history.json --protocol protocol.json --lock experiment.lock.json --fold development --output-dir development-report
```

Run `validation` and then `holdout` into fresh output directories. Supply the same optional `--policy` file at freeze and run if it differs from the repo default. The lock covers the input files, replay code, Python and numeric library versions. Keep the final lock and data vintage; publish the lock or otherwise commit to it before looking at holdout outcomes. A local hash prevents accidental input drift. It does not prove that the holdout was never opened or that variants were never tried. Changing the protocol after inspecting a holdout requires a fresh untouched holdout.

## Input contract (version 1 JSON)

Root keys: `version: 1`, `kind: "historical"` or `"synthetic"`, `source`, `benchmark_security_id`, `attestations`, and the following arrays. Dates use ISO `YYYY-MM-DD`; timestamps must carry UTC offsets. Use US USD ordinary equities and one tradable broad-market proxy; include dividends on the proxy so its return is comparable. Keep licensed data outside the repository.

| Array | Required fields and conventions |
|---|---|
| `sessions` | `date`, `open_at`, `close_at` for every regular exchange session, including early closes; unique, chronological, no synthetic weekend or holiday bars in historical runs. Include warm-up and all dates through the holdout end. |
| `securities` | `security_id`, `issuer_id`, `currency: "USD"`, `kind`: `ordinary`, `benchmark`, or `distribution`. IDs must survive symbol changes; reuse a ticker only with a distinct ID for a different security. Use `distribution` for successor legs outside the eligible universe. |
| `membership` | `security_id`, effective `session`, `available_at`, `ticker`, boolean `active`, `source_id`. Include membership starts, changes and removals for historical names, including failures. Do not substitute today's index or watchlist. |
| `bars` | `security_id`, `session`, raw split-unadjusted `open`, `close`, `volume`; null means missing. An optional `close_available_at` delays close and volume visibility; if absent the runner assumes an immutable tape published at the session close. A missing entire bar is not compressed out of the signal lookback or filled from a later session. Store only raw observations or explicitly delayed values, not retrospectively adjusted history. |
| `facts` | `security_id`, `period_end`, `available_at`, `source_id`, `sector`, `shares_outstanding`. Optional `shares_asof` defaults to `period_end`. Use the original observation date for a later filing cover count and apply only splits after that date. Optional `industry`, `evidence`, `filing_status`, `event_hold`. See `backtest_demo.snapshot()` for the scanner evidence shape. Set `filing_status: "METADATA_CHECKED"` and `event_hold: false` only from dated evidence. Snapshot availability must be the latest availability time of any bundled field. To incorporate a restatement of an earlier year in the current snapshot, publish a new vintage of that current snapshot; do not rewrite it at the old cutoff. |
| `actions` | `security_id`, pre-open effective `session`, terms `available_at`, `kind`, `source_id`, and the fields below. Use terms per post-split share when a split and payout share an effective date. |

Action kinds and settlement:

- `split`: `ratio` new shares per old share. Reverse splits use ratios below one.
- `dividend`, `capital_gain`, `rights_cash`: explicit `cash_per_share`; optional `pay_session` defaults to the effective session. Rights are supported only as an evidenced cash realization, with no assumed exercise.
- `spin_off`: `successor_id` and `ratio`. Shares are carried to the original holding's exit. The parent is not treated as an eligible drawdown while its price window includes the unadjusted spin-off discontinuity.
- `merger`, `bankruptcy`, `distressed_delisting`, `ordinary_delisting`: remove the old shares; provide cash and/or stock consideration. Stock terms require `successor_id`, `ratio` and an explicit cash amount (zero for stock-only). For cash-only outcomes, **zero is verified zero**; null means unresolved. No old-security bars are allowed from the effective session onward. Consolidate same-session successor actions before importing. Split and successor share terms must be available by the effective open.
- A disclosed cash receivable is marked at face value and becomes spendable at the first open on or after settlement and disclosure. For a confirmed positive amount with an unverified payment date, use `pay_session: null`. The ledger carries a provisional receivable, leaves the outcome unresolved for coverage and keeps the proceeds out of buying power. Omitting `pay_session` assumes payment at the effective session. Terminal cash unknown within a fold stays unresolved. Zero and last observed mark are sensitivity scenarios, not upper/lower statistical bounds or inferred delisting proceeds.

The historical attestations are `dated_membership_includes_failures`, `vintage_facts`, `raw_unadjusted_bars`, `exchange_sessions`, and `corporate_actions_and_terminal_outcomes`. Set them to true only after independently auditing the supplier's coverage. The runner enforces dates and known identities, but cannot detect omitted securities or certify a vendor's history from one file.

## Execution and interpretation

- Signals are evaluated at the regular session close on the frozen schedule. Orders reference the next regular open; missing opens skip, and no later bar substitutes. Position size uses prior close NAV, known settled cash, position/issuer limits and trailing dollar volume. Caps use lagged volume; failed exit fills are unresolved, rather than priced at a later favorable quote.
- Six-, twelve- and twenty-four-month books are independent. Each fixed horizon exits at the first regular open on/after the planned deadline. Signals are purged when that exit would cross a fold boundary. Cash or stock consideration may realize a terminal outcome earlier. +50% (183/365 days) and +100% (730 days) close touches are separate from net proceeds at exit; a touch is not an executed take-profit order.
- Commission, half-spread, slippage and square-root impact are charged on fills at base and double cost. Fractional shares are a simulation convenience. No leverage, shorting, tax, funding interest, intraday fills, or position rolls across folds are modeled. Spin-offs and stock mergers can create involuntary issuer exposure.
- The same universe, timing, position limits and cost model apply to the active comparators. Matched orders use same-sector controls inside the frozen cap/liquidity calipers for actual scanner entry slots. Unmatched or missed fills are reported; the market proxy holds through the fold with one budget slot.
- `report.md` is a summary; `report.json` records all cost/recovery scenarios, paired comparisons, coverage and gate reasons. `signals-*.json` records cutoffs, fact/membership source IDs and ranks. `ledger-*.json` preserves trades, skipped-order counts, daily NAV and provisional marks. Short samples suppress inference; paired circular blocks are at least the horizon in approximate trading sessions. The confidence intervals are familywise-adjusted across frozen comparisons. Gates also require sufficient fills, coverage, both time halves, bounded issuer concentration and severe-loss rates.
- Only an attested historical holdout can report `GATE_MET_FOR_CORE_ONLY`. That result is conditional on data quality, costs and the frozen settings; it is not proof of live performance. Add markets and full production parity only after the US core and its inputs are audited. Evaluate AI prospectively rather than allowing current models to see historical outcomes.
