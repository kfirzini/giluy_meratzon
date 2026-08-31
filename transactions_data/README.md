# Wallet transaction data

This directory is organized into one authoritative raw layer and one clean
summary layer:

```text
transactions_data/
├── raw/
│   ├── bitcoin_transactions.csv
│   └── ethereum_transactions.csv
├── summaries/
│   ├── all_transactions.csv
│   └── yearly_sales_summary.csv
├── tax/
│   ├── fifo_allocations.csv
│   ├── historical_nis_prices.csv
│   ├── nis_value_overrides.csv
│   ├── tax_by_transaction.csv
│   └── tax_by_year.csv
├── README.md
└── sources.json
```

## Refresh

Run both commands from the repository root:

```bash
python3 scripts/fetch_wallet_tables.py
python3 scripts/build_transaction_summaries.py
python3 scripts/build_tax_tables.py
```

The fetch script reads every Ethereum address and the Bitcoin ypub from
`personal_data.md`. It queries Blockscout and mempool.space, fetches all
available history, scans both Bitcoin branches with a gap limit of 20, and
deduplicates Ethereum events returned for more than one owned wallet. It uses no API
keys or third-party Python packages. Existing tables are not replaced until
all network fetching has succeeded.

`sources.json` records the refresh time, source endpoints, per-wallet counts,
deduplication count, and final raw row counts.

## Summary rules

`summaries/all_transactions.csv` is an asset-flow table. A zero-value Ethereum
parent call is combined with its token/internal event, so a transaction hash
can still have multiple rows only when it contains multiple distinct asset
events.

Classification is applied in this order:

1. Failed/reverted transactions are `failed` and have transferred amount `0`.
2. Token look-alikes that impersonate ETH and unsolicited token dust are
   `airdrop/spam`.
3. A transfer whose two endpoints are configured wallets is
   `moving between my wallets`.
4. The 20 ETH transaction whose on-chain method is `stake` is `staking`.
5. Genuine owned-to-external transfers are `selling`, based on the prior
   wallet note that outward transfers were sales except staking.
6. External-to-owned asset transfers with acquisition evidence are `buying`.
7. Zero-value calls and approvals are `contract interaction`.

Amounts never include fees. Ethereum gas and Bitcoin miner fees are separate
`fee`/`fee_coin` columns. The outgoing Bitcoin amount is the external output,
not the wallet balance change, so it excludes both change and the miner fee.
All timestamps are UTC at whole-second precision.

`summaries/yearly_sales_summary.csv` has one row for every year in the covered
period. Counts use distinct transaction hashes. Amounts remain grouped by coin
because units such as ETH, BTC, BNT, and EOS cannot be added together.

Raw tables contain blockchain facts only; they do not contain fiat prices,
cost basis, gains, losses, or tax calculations.

## Estimated BTC/ETH tax workpaper

`scripts/build_tax_tables.py` filters the summary to confirmed BTC and ETH
`buying` and `selling` rows. It excludes tokens, airdrop/spam, staking,
own-wallet movements, contract interactions, and failed transactions. It then
uses FIFO separately for BTC and ETH and applies a 25% tax rate to positive
annual gains. Losses are netted only within the same year; the table does not
apply losses carried from another year.

The blockchain does not record the actual NIS paid or received. By default,
the workpaper therefore estimates each transaction's NIS value using the
nearest Coinbase one-minute BTC/USD or ETH/USD closing price and the daily
Frankfurter USD/ILS reference rate. Those source observations are retained in
`tax/historical_nis_prices.csv`. Network fees on sale rows are valued using the
same transaction price and treated as sale expenses.

For filing-quality calculations, enter bank or exchange evidence in
`tax/nis_value_overrides.csv`:

- `gross_value_nis`: total actual NIS paid for a buy or received for a sale.
- `sale_expenses_nis`: actual deductible sale expenses, if applicable.
- `evidence_or_notes`: a reference to the supporting statement or receipt.

Blank override cells continue to use the cached market-price estimate. The
script preserves completed override cells when it refreshes the template.
`tax_by_transaction.csv` is the simple sale-level table,
`tax_by_year.csv` is the annual summary, and `fifo_allocations.csv` is the
supporting purchase-lot audit trail. Annual `ALL` rows are the combined BTC and
ETH totals; do not add the asset rows to the `ALL` row again.
