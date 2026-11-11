# Historical data: acquisition and acceptance checklist

## Source decision

| Source | What it can supply | What is still missing or must be verified |
|---|---|---|
| [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and [as-filed XBRL datasets](https://www.sec.gov/dera/data/financial-statement-data-sets.html) | Public filing IDs, acceptance metadata and accession-linked numeric facts. No API purchase is needed for the bounded audit. | Not a trading tape, membership history or payout database. Need issuer-to-security links, context and duration reconciliation, and archived event-review evidence. The SEC does [not guarantee dissemination delay or expose first public availability](https://www.sec.gov/about/webmaster-frequently-asked-questions); the pilot waits to the following New York calendar day after acceptance and filing. This is a conservative replay convention, not a vendor timestamp. |
| [CRSP US daily equities (CIZ)](https://www.crsp.org/research/crsp-us-stock-databases-2025-layout/) + [Compustat Snapshot](https://www.marketplace.spglobal.com/en/datasets/compustat-financials-%288%29), if already licensed | Preferred institutional route: stable security/issuer identifiers, active and inactive listings, market events, and historical statement vintages. Use dated CRSP/Compustat links rather than matching today's tickers. | Confirm access to the **daily** files, not a monthly workbook; confirm snapshot/dated link entitlement, point-in-time classification, and usable terminal consideration. [CIZ's delisting return, amount and successor fields](https://www.crsp.org/wp-content/uploads/guides/CRSP_US_Stock_%26_Indexes_Database_Guide_Flat_File_Format_2.0.pdf) are not interchangeable with cash paid per share. Inspect missing codes, settlement timing and stock/cash splits before importing. |
| [Norgate US Platinum](https://norgatedata.com/stockmarketpackages.php) + SEC | Candidate retail market-data route: the published Platinum plan lists inactive securities and effective-dated index membership. The [trial FAQ](https://norgatedata.com/data-package-faq.php) says the trial history is limited to two years. | A trial can validate ingestion, not support the planned holdout. The FAQ says historical industry classifications and constituent announcement dates are not supplied. Verify raw open/close/volume, usable actions, OTC continuation, terminal consideration and local retention/export rights before purchasing. SEC financial normalization would still be required. |
| [Nasdaq Data Link Sharadar SEP](https://data.nasdaq.com/databases/SEP/documentation?anchor=sample-data) + [SF1](https://data.nasdaq.com/databases/SF1/documentation?anchor=see-also) | Alternative vendor to sample: historical active and inactive US pricing, action/reference tables and as-reported fundamental dimensions. | Verify the basis of **each** OHLC/volume field, date-key availability, stable issuer/security mapping, effective-dated membership and terminal proceeds. A delisted ticker and last quote alone do not identify economic recovery. Do not buy on catalog coverage claims alone. |

Start with a fixed, dated US universe and the 365-day horizon. Keep trial and development records out of the final holdout. The default uncertainty gate requires at least eight nominal horizon-length blocks; a two-year sample cannot satisfy it. Do not pool older 24-month results or choose a new universe after seeing the final result.

## First export to request from a provider

Before a full pull, ask for a small, licensed sample for a continuing issuer, a cash merger, a stock merger or spin-off, a distressed delisting that moved to OTC, and a bankruptcy cancellation. Include a broad-market proxy. Retain the provider's source field definitions and data vintage beside the sample.

1. Dated security and issuer IDs, aliases, exchange, share class and membership/listing effective intervals. A ticker is a label, not a key.
2. Actual trading sessions and raw daily open, close and volume, with explicit missing codes and any delayed availability. An adjusted close cannot supply an executable raw open.
3. Effective date, known date, pay date and per-share basis for splits, distributions and successor consideration. Separate exchange removal, OTC continuation and final economic settlement. A confirmed zero recovery is distinct from missing proceeds.
4. Statement period, first availability, vintage/version, original units, source ID, historical sector and shares. For a complete development run provide enough earlier fiscal periods to normalize FCF; a sample around one event is only a mapping check.
5. Spot-check those cases against issuer filings and the provider's tape before marking any dataset attestation true. Store licensed inputs and generated ledgers outside the public repository.

The former Bed Bath & Beyond is a useful regression case: the [Nasdaq removal notice](https://www.sec.gov/Archives/edgar/data/886158/000135445723000478/bbbydelistreason.txt) specifies an exchange removal date, the [issuer annual filing](https://www.sec.gov/Archives/edgar/data/886158/000088615823000059/bbby-20230225.htm) describes OTC quotation, and the [later 8-K](https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/d579010d8k.htm) reports the effective plan and share cancellation. Treat them as different facts. The EDGAR tool emits notices, never an assumed cash or stock payout.

## Public first-stage adapter

```sh
python edgar_vintages.py --cik 320193 --cik 886158 --start 2023-01-01 --end 2023-12-31 --as-of 2024-01-05T00:00:00Z --output edgar-vintage-audit.json
```

The report joins submission metadata to candidate XBRL values by accession and fiscal end, retains amendments independently, leaves conflicting tags visible, and preserves each original duration and unit. It is intentionally labeled `edgar_vintage_audit_only`, outside the replay input format. It does not build TTM values, manufacture financial clearance, or attempt a performance estimate. The GitHub pilot runs without a paid API or credentials for a data vendor.
