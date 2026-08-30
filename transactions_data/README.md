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
├── README.md
└── sources.json
```

## Refresh

Run both commands from the repository root:

```bash
python3 scripts/fetch_wallet_tables.py
python3 scripts/build_transaction_summaries.py
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
