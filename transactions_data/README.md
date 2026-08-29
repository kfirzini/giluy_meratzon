# Wallet transaction tables

This directory contains one simple CSV table for each wallet listed in
`../personal_data.md`:

- `ethereum_transactions.csv`
- `bitcoin_transactions.csv`

The tables contain blockchain transaction facts only. They do not contain
prices, fiat values, cost basis, gains, losses, or tax classifications.

The Ethereum table keeps native transactions, internal ETH movements, and
token transfers in one file. `record_type` identifies which source record each
row represents. A transaction hash can therefore appear more than once when a
transaction contains a token or internal transfer.

The Bitcoin table contains one row per unique transaction. `wallet_net_sats`
and `wallet_net_btc` are the transaction's signed effect on the wallet; they are
unit/balance representations, not tax calculations. Both external and change
branches are scanned with a gap limit of 20.

`sources.json` records the source and row counts. Ethereum data comes directly
from Blockscout, and Bitcoin data comes directly from mempool.space.

To refresh both tables from the repository root:

```bash
python3 scripts/fetch_wallet_tables.py
```

The refresh requires network access but no API keys or third-party Python
packages.
