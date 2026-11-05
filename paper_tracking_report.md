# Forward paper tracking

Hypothetical entries use the next session's opening price. Returns are in the listing currency, dividend/split adjusted, before costs and taxes.
Daily selections can repeat the same stock. These are correlated observations, not independent trades or a portfolio backtest.

Saved selections: 3. Completed twelve-month observations under method v3: 0.

Stored status counts (older methods may need refresh): tracking: 3

Unverified/stale names remain visible; their missing outcomes must not be interpreted as zero losses. USD observations compare against dividend/split-adjusted SPY at the same entry and mark sessions. Non-USD comparisons remain unsupported; no FX conversion is performed. Excess is a percentage-point difference, not risk-adjusted alpha.

Completion requires usable holding-window closes, no duplicate sessions, no observed gap over ten calendar days and consistent supplied OHLC bounds. This coarse guard cannot detect every missing exchange session or verify delisting proceeds. Older completed metrics require refresh under the current method.

## Cohorts

Groups keep financial policy, price-screen cohort and research status as recorded at selection. Legacy/unknown values remain separate. Counts of +50%, doubled or losing outcomes use current-method completed observations only; unresolved outcomes remain in the total. These counts do not establish a success probability or a bankruptcy/delisting rate.

| Policy | Price screen | Research status | Observations | Unique tickers | Pending | Tracking | Unverified/stale/old method | Complete | Touched +50% | Ended +50% | Touched 2x | Ended 2x | Ended below entry |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 72aca0f0daf9 | stabilizing_drawdown | legacy/unknown | 3 | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Most recent 20 selections

| Selected | Ticker | Status | Local return | Entry session | Mark session | SPY return | Stock minus SPY |
|---|---|---|---:|---|---|---:|---:|
| 2026-10-21 | SFD | tracking | +7.0% | 2026-10-22 | 2026-11-04 | +0.1% | +6.9 pp |
| 2026-10-21 | LRN | tracking | +1.3% | 2026-10-22 | 2026-11-04 | +0.1% | +1.2 pp |
| 2026-10-21 | LCII | tracking | +25.6% | 2026-10-22 | 2026-11-04 | +0.1% | +25.6 pp |
