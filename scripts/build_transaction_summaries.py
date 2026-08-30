#!/usr/bin/env python3
"""Build clean transaction and yearly sell/staking summaries from raw wallet facts."""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from fetch_wallet_tables import format_units, load_wallets


RAW_DIRECTORY = Path("transactions_data/raw")
SUMMARY_DIRECTORY = Path("transactions_data/summaries")
ETHEREUM_CSV = RAW_DIRECTORY / "ethereum_transactions.csv"
BITCOIN_CSV = RAW_DIRECTORY / "bitcoin_transactions.csv"
ALL_TRANSACTIONS_CSV = SUMMARY_DIRECTORY / "all_transactions.csv"
YEARLY_SUMMARY_CSV = SUMMARY_DIRECTORY / "yearly_sales_summary.csv"

TYPE_BUYING = "buying"
TYPE_SELLING = "selling"
TYPE_MOVING = "moving between my wallets"
TYPE_STAKING = "staking"
TYPE_AIRDROP_SPAM = "airdrop/spam"
TYPE_CONTRACT = "contract interaction"
TYPE_FAILED = "failed"

ALL_TYPES = {
    TYPE_BUYING,
    TYPE_SELLING,
    TYPE_MOVING,
    TYPE_STAKING,
    TYPE_AIRDROP_SPAM,
    TYPE_CONTRACT,
    TYPE_FAILED,
}

# These are the real token contracts with evidence of acquisition rather than an
# unsolicited distribution. Other inbound tokens remain visible but are labeled
# airdrop/spam instead of being guessed to be purchases.
ACQUIRED_TOKEN_CONTRACTS = {
    "0x1f573d6fb3f13d689ff844b4ce37794d79a7ff1c",  # BNT
    "0x86fa049857e0209aa7d9e616f7eb3b3b78ecfdb0",  # EOS
    "0x0cf0ee63788a0849fe5297f3407f701e122cc023",  # XDATA
    "0xb1cd6e4153b2a390cf00a6556b0fc1458c4a5533",  # ETHBNT
}

# The token feed contains look-alike "ETH" contracts used for address poisoning.
# Native ETH is represented only by native/internal records, never token records.
CYRILLIC_LOOKALIKES = str.maketrans(
    {"Е": "E", "е": "e", "Т": "T", "т": "t", "Н": "H", "н": "h"}
)

TRANSACTION_COLUMNS = [
    "date",
    "type",
    "amount",
    "coin_type",
    "fee",
    "fee_coin",
    "network",
    "from",
    "to",
    "transaction_hash",
    "status",
    "source_record_type",
    "event_index",
    "token_contract",
    "source_url",
    "notes",
]

YEARLY_COLUMNS = [
    "year",
    "sell_transactions",
    "total_sold_by_coin",
    "staking_transactions",
    "total_staked_by_coin",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def normalize_timestamp(value: str) -> str:
    """Return UTC ISO-8601 timestamps at whole-second precision."""
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:Z|\+00:00)",
        value,
    )
    if not match:
        raise ValueError(f"unsupported timestamp: {value!r}")
    return f"{match.group(1)}T{match.group(2)}Z"


def is_zero(value: str) -> bool:
    return value != "" and Decimal(value) == 0


def format_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def canonical_symbol(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(CYRILLIC_LOOKALIKES)
    return "".join(character for character in value.upper() if character.isascii() and character.isalpha())


def is_eth_lookalike_token(row: dict[str, str]) -> bool:
    return row["record_type"] == "token_transfer" and canonical_symbol(row["asset"]) == "ETH"


def blank_transaction() -> dict[str, str]:
    return {column: "" for column in TRANSACTION_COLUMNS}


def compact_addresses(value: str) -> str:
    addresses = [address for address in value.split(";") if address]
    if len(addresses) <= 3:
        return ";".join(addresses)
    return f"{len(addresses)} external addresses (see raw table)"


def classify_ethereum_row(
    row: dict[str, str], owned: set[str]
) -> tuple[str, str]:
    from_owned = row["from_address"].lower() in owned
    to_owned = row["to_address"].lower() in owned

    if row["status"] != "ok":
        return TYPE_FAILED, "reverted/failed on-chain transaction; no asset transferred"

    if from_owned and to_owned:
        return TYPE_MOVING, "both endpoints are configured owned wallets"

    if row["record_type"] == "token_transfer" and is_eth_lookalike_token(row):
        return TYPE_AIRDROP_SPAM, "non-native token impersonates ETH; excluded from sales"

    if from_owned and row["method"].lower() == "stake":
        return TYPE_STAKING, "Blockscout method is stake"

    if row["record_type"] == "token_transfer":
        if from_owned:
            return TYPE_SELLING, "genuine owned-to-external token transfer; prior wallet note identifies outward transfers as sales"
        if to_owned and row["token_contract"].lower() in ACQUIRED_TOKEN_CONTRACTS:
            return TYPE_BUYING, "external-to-owned transfer of a documented acquired token"
        return TYPE_AIRDROP_SPAM, "unsolicited token distribution/dust; no purchase evidence"

    if from_owned:
        if is_zero(row["amount"]):
            return TYPE_CONTRACT, "zero-value call/approval; only a network fee moved"
        return TYPE_SELLING, "owned-to-external transfer; prior wallet note identifies outward transfers as sales"

    if to_owned:
        if is_zero(row["amount"]):
            return TYPE_AIRDROP_SPAM, "zero-value inbound transaction"
        return TYPE_BUYING, "external-to-owned asset transfer"

    raise ValueError(f"Ethereum row does not touch an owned wallet: {row['transaction_hash']}")


def build_ethereum_transactions(
    raw_rows: list[dict[str, str]], owned: set[str]
) -> list[dict[str, str]]:
    child_hashes = {
        row["transaction_hash"].lower()
        for row in raw_rows
        if row["record_type"] != "native_transaction"
    }
    fee_by_hash = {
        row["transaction_hash"].lower(): row["transaction_fee_eth"]
        for row in raw_rows
        if row["record_type"] == "native_transaction"
        and row["from_address"].lower() in owned
        and row["transaction_fee_eth"] != ""
    }

    transactions: list[dict[str, str]] = []
    for raw in raw_rows:
        tx_hash = raw["transaction_hash"].lower()

        # A zero-value parent call and its token/internal event are one economic
        # transaction. Keep the asset event and attach the parent's fee later.
        if (
            raw["record_type"] == "native_transaction"
            and raw["status"] == "ok"
            and is_zero(raw["amount"])
            and tx_hash in child_hashes
        ):
            continue

        transaction_type, notes = classify_ethereum_row(raw, owned)
        output = blank_transaction()
        output.update(
            {
                "date": normalize_timestamp(raw["timestamp_utc"]),
                "type": transaction_type,
                "amount": "0" if transaction_type == TYPE_FAILED else raw["amount"],
                "coin_type": raw["asset"],
                "fee_coin": "ETH" if tx_hash in fee_by_hash else "",
                "network": "Ethereum",
                "from": raw["from_address"],
                "to": raw["to_address"],
                "transaction_hash": raw["transaction_hash"],
                "status": raw["status"],
                "source_record_type": raw["record_type"],
                "event_index": raw["event_index"],
                "token_contract": raw["token_contract"],
                "source_url": raw["source_url"],
                "notes": notes,
            }
        )
        if raw["amount"] == "":
            output["notes"] += "; amount unavailable because token decimals are missing"
        transactions.append(output)

    transactions.sort(
        key=lambda row: (
            row["date"],
            row["transaction_hash"].lower(),
            row["source_record_type"],
            row["event_index"],
        )
    )

    fee_assigned: set[str] = set()
    for row in transactions:
        tx_hash = row["transaction_hash"].lower()
        if tx_hash in fee_by_hash and tx_hash not in fee_assigned:
            row["fee"] = fee_by_hash[tx_hash]
            fee_assigned.add(tx_hash)
        elif tx_hash not in fee_by_hash:
            row["fee_coin"] = ""
    return transactions


def build_bitcoin_transactions(raw_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    transactions: list[dict[str, str]] = []
    for raw in raw_rows:
        wallet_input = int(raw["wallet_input_sats"])
        wallet_output = int(raw["wallet_output_sats"])
        external_output = int(raw["external_output_sats"])
        confirmed = raw["confirmed"].lower() == "true"

        output = blank_transaction()
        output.update(
            {
                "date": normalize_timestamp(raw["timestamp_utc"]),
                "coin_type": "BTC",
                "network": "Bitcoin",
                "transaction_hash": raw["transaction_hash"],
                "status": "confirmed" if confirmed else "pending",
                "source_record_type": "bitcoin_transaction",
                "source_url": raw["source_url"],
            }
        )

        if wallet_input == 0:
            output.update(
                {
                    "type": TYPE_BUYING,
                    "amount": format_units(wallet_output, 8),
                    "from": compact_addresses(raw["external_input_addresses"]),
                    "to": raw["wallet_output_addresses"],
                    "notes": "external-to-owned Bitcoin transfer",
                }
            )
        elif external_output == 0:
            output.update(
                {
                    "type": TYPE_MOVING,
                    "amount": format_units(wallet_output, 8),
                    "from": raw["wallet_input_addresses"],
                    "to": raw["wallet_output_addresses"],
                    "fee": raw["transaction_fee_btc"],
                    "fee_coin": "BTC",
                    "notes": "all spendable outputs return to derived addresses in the configured wallet",
                }
            )
        else:
            output.update(
                {
                    "type": TYPE_SELLING,
                    "amount": format_units(external_output, 8),
                    "from": raw["wallet_input_addresses"],
                    "to": raw["external_output_addresses"],
                    "fee": raw["transaction_fee_btc"],
                    "fee_coin": "BTC",
                    "notes": "owned-to-external transfer; amount is external output and excludes miner fee",
                }
            )
        transactions.append(output)
    return transactions


def format_amounts(amounts: dict[str, Decimal]) -> str:
    if not amounts:
        return "0"
    priority = {"ETH": 0, "BTC": 1}
    coins = sorted(amounts, key=lambda coin: (priority.get(coin, 2), coin))
    return "; ".join(f"{format_decimal(amounts[coin])} {coin}" for coin in coins)


def build_yearly_summary(transactions: list[dict[str, str]]) -> list[dict[str, str | int]]:
    first_year = min(int(row["date"][:4]) for row in transactions)
    last_year = max(int(row["date"][:4]) for row in transactions)
    rows: list[dict[str, str | int]] = []

    for year in range(first_year, last_year + 1):
        year_rows = [row for row in transactions if int(row["date"][:4]) == year]
        sells = [row for row in year_rows if row["type"] == TYPE_SELLING]
        stakes = [row for row in year_rows if row["type"] == TYPE_STAKING]
        sold: dict[str, Decimal] = defaultdict(Decimal)
        staked: dict[str, Decimal] = defaultdict(Decimal)

        for row in sells:
            if row["amount"] != "":
                sold[row["coin_type"]] += Decimal(row["amount"])
        for row in stakes:
            if row["amount"] != "":
                staked[row["coin_type"]] += Decimal(row["amount"])

        rows.append(
            {
                "year": year,
                "sell_transactions": len(
                    {(row["network"], row["transaction_hash"].lower()) for row in sells}
                ),
                "total_sold_by_coin": format_amounts(sold),
                "staking_transactions": len(
                    {(row["network"], row["transaction_hash"].lower()) for row in stakes}
                ),
                "total_staked_by_coin": format_amounts(staked),
            }
        )
    return rows


def validate(
    transactions: list[dict[str, str]], yearly: list[dict[str, str | int]], owned: set[str]
) -> None:
    if not transactions:
        raise ValueError("no transactions were produced")
    if any(row["type"] not in ALL_TYPES for row in transactions):
        raise ValueError("unknown transaction type in summary")
    if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", row["date"]) for row in transactions):
        raise ValueError("summary contains a non-normalized timestamp")
    for row in transactions:
        if (
            row["network"] == "Ethereum"
            and row["from"].lower() in owned
            and row["to"].lower() in owned
            and row["type"] != TYPE_MOVING
        ):
            raise ValueError(f"owned-to-owned row was not classified as movement: {row['transaction_hash']}")
        if row["type"] in {TYPE_SELLING, TYPE_STAKING} and row["amount"] == "":
            raise ValueError(f"economic total has an unknown amount: {row['transaction_hash']}")
    if len(yearly) != int(yearly[-1]["year"]) - int(yearly[0]["year"]) + 1:
        raise ValueError("yearly summary is not contiguous")


def main() -> None:
    ethereum_wallets, _ = load_wallets()
    owned = {wallet.lower() for wallet in ethereum_wallets}
    ethereum = build_ethereum_transactions(read_csv(ETHEREUM_CSV), owned)
    bitcoin = build_bitcoin_transactions(read_csv(BITCOIN_CSV))
    transactions = sorted(
        ethereum + bitcoin,
        key=lambda row: (
            row["date"],
            row["network"],
            row["transaction_hash"].lower(),
            row["source_record_type"],
            row["event_index"],
        ),
    )
    yearly = build_yearly_summary(transactions)
    validate(transactions, yearly, owned)
    write_csv(ALL_TRANSACTIONS_CSV, TRANSACTION_COLUMNS, transactions)
    write_csv(YEARLY_SUMMARY_CSV, YEARLY_COLUMNS, yearly)
    print(
        f"Wrote {len(transactions)} transaction rows and {len(yearly)} yearly rows"
    )


if __name__ == "__main__":
    main()
