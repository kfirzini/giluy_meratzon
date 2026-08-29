#!/usr/bin/env python3
"""Fetch simple, calculation-free transaction tables for the configured wallets."""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WALLET_FILE = Path("personal_data.md")
OUTPUT_DIRECTORY = Path("transactions_data")
ETHEREUM_CSV = OUTPUT_DIRECTORY / "ethereum_transactions.csv"
BITCOIN_CSV = OUTPUT_DIRECTORY / "bitcoin_transactions.csv"
SOURCES_FILE = OUTPUT_DIRECTORY / "sources.json"

BLOCKSCOUT_API = "https://eth.blockscout.com/api/v2"
BLOCKSCOUT_SITE = "https://eth.blockscout.com"
MEMPOOL_API = "https://mempool.space/api"
MEMPOOL_SITE = "https://mempool.space"
USER_AGENT = "giluy-meratzon-transaction-table/1.0"
GAP_LIMIT = 20

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
FIELD_PRIME = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
CURVE_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GENERATOR = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def http_get(url: str, attempts: int = 6) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            last_error = error
            retryable = not isinstance(error, urllib.error.HTTPError) or error.code in {
                408,
                425,
                429,
                500,
                502,
                503,
                504,
            }
            if not retryable or attempt == attempts - 1:
                break
            time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"request failed: {url}: {last_error}")


def get_json(url: str) -> Any:
    return json.loads(http_get(url).decode("utf-8"))


def paginated_items(endpoint: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    params: dict[str, Any] | None = None
    seen: set[str] = set()
    while True:
        url = endpoint
        if params:
            encoded = urllib.parse.urlencode(params)
            if encoded in seen:
                raise RuntimeError(f"pagination loop: {endpoint}")
            seen.add(encoded)
            url += "?" + encoded
        response = get_json(url)
        items.extend(response.get("items", []))
        params = response.get("next_page_params")
        if not params:
            return items
        time.sleep(0.15)


def load_wallets() -> tuple[str, str]:
    text = WALLET_FILE.read_text(encoding="utf-8")
    ethereum = re.findall(r"\b0x[0-9a-fA-F]{40}\b", text)
    bitcoin = re.findall(r"\bypub[1-9A-HJ-NP-Za-km-z]{90,120}\b", text)
    if len(ethereum) != 1 or len(bitcoin) != 1:
        raise ValueError("expected exactly one Ethereum address and one Bitcoin ypub")
    return ethereum[0], bitcoin[0]


def format_units(raw_value: str | int | None, decimals: str | int | None) -> str:
    if raw_value in (None, "") or decimals in (None, ""):
        return ""
    raw = int(raw_value)
    precision = int(decimals)
    sign = "-" if raw < 0 else ""
    digits = str(abs(raw)).rjust(precision + 1, "0")
    if precision == 0:
        return sign + digits
    whole = digits[:-precision]
    fraction = digits[-precision:].rstrip("0")
    return sign + whole + ("." + fraction if fraction else "")


def address_hash(value: Any) -> str:
    return value.get("hash", "") if isinstance(value, dict) else ""


ETHEREUM_COLUMNS = [
    "record_type",
    "timestamp_utc",
    "transaction_hash",
    "block_number",
    "event_index",
    "status",
    "from_address",
    "to_address",
    "asset",
    "amount",
    "amount_raw",
    "decimals",
    "transaction_fee_eth",
    "transaction_fee_wei",
    "method",
    "token_contract",
    "source_url",
]


def fetch_ethereum_table(wallet: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    base = f"{BLOCKSCOUT_API}/addresses/{wallet}"
    transactions = paginated_items(base + "/transactions")
    internal = paginated_items(base + "/internal-transactions")
    token_transfers = paginated_items(base + "/token-transfers")
    rows: list[dict[str, Any]] = []

    for item in transactions:
        fee_wei = item.get("fee", {}).get("value", "")
        tx_hash = item.get("hash", "")
        rows.append(
            {
                "record_type": "native_transaction",
                "timestamp_utc": item.get("timestamp", ""),
                "transaction_hash": tx_hash,
                "block_number": item.get("block_number", ""),
                "event_index": "",
                "status": item.get("status", ""),
                "from_address": address_hash(item.get("from")),
                "to_address": address_hash(item.get("to")),
                "asset": "ETH",
                "amount": format_units(item.get("value"), 18),
                "amount_raw": item.get("value", ""),
                "decimals": 18,
                "transaction_fee_eth": format_units(fee_wei, 18),
                "transaction_fee_wei": fee_wei,
                "method": item.get("method") or "",
                "token_contract": "",
                "source_url": f"{BLOCKSCOUT_SITE}/tx/{tx_hash}",
            }
        )

    for item in internal:
        tx_hash = item.get("transaction_hash", "")
        rows.append(
            {
                "record_type": "internal_transaction",
                "timestamp_utc": item.get("timestamp", ""),
                "transaction_hash": tx_hash,
                "block_number": item.get("block_number", ""),
                "event_index": item.get("index", ""),
                "status": "ok" if item.get("success") else "error",
                "from_address": address_hash(item.get("from")),
                "to_address": address_hash(item.get("to")),
                "asset": "ETH",
                "amount": format_units(item.get("value"), 18),
                "amount_raw": item.get("value", ""),
                "decimals": 18,
                "transaction_fee_eth": "",
                "transaction_fee_wei": "",
                "method": item.get("type", ""),
                "token_contract": "",
                "source_url": f"{BLOCKSCOUT_SITE}/tx/{tx_hash}",
            }
        )

    for item in token_transfers:
        tx_hash = item.get("transaction_hash", "")
        token = item.get("token") or {}
        total = item.get("total") or {}
        decimals = total.get("decimals", token.get("decimals", ""))
        amount_raw = total.get("value", "")
        rows.append(
            {
                "record_type": "token_transfer",
                "timestamp_utc": item.get("timestamp", ""),
                "transaction_hash": tx_hash,
                "block_number": item.get("block_number", ""),
                "event_index": item.get("log_index", ""),
                "status": "ok",
                "from_address": address_hash(item.get("from")),
                "to_address": address_hash(item.get("to")),
                "asset": token.get("symbol") or token.get("name") or item.get("token_type", ""),
                "amount": format_units(amount_raw, decimals),
                "amount_raw": amount_raw,
                "decimals": decimals,
                "transaction_fee_eth": "",
                "transaction_fee_wei": "",
                "method": item.get("method") or "",
                "token_contract": token.get("address_hash", ""),
                "source_url": f"{BLOCKSCOUT_SITE}/tx/{tx_hash}",
            }
        )

    rows.sort(
        key=lambda row: (
            row["timestamp_utc"],
            str(row["transaction_hash"]),
            str(row["record_type"]),
            str(row["event_index"]),
        )
    )
    return rows, {
        "native_transactions": len(transactions),
        "internal_transactions": len(internal),
        "token_transfers": len(token_transfers),
        "table_rows": len(rows),
    }


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def ripemd160(data: bytes) -> bytes:
    return hashlib.new("ripemd160", data).digest()


def base58_decode(value: str) -> bytes:
    number = 0
    for character in value:
        number = number * 58 + BASE58_ALPHABET.index(character)
    leading = len(value) - len(value.lstrip("1"))
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * leading + body


def base58_encode(value: bytes) -> str:
    leading = len(value) - len(value.lstrip(b"\x00"))
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    return "1" * leading + encoded


def base58check(payload: bytes) -> str:
    return base58_encode(payload + sha256(sha256(payload))[:4])


def inverse(value: int) -> int:
    return pow(value, FIELD_PRIME - 2, FIELD_PRIME)


def point_add(
    left: tuple[int, int] | None, right: tuple[int, int] | None
) -> tuple[int, int] | None:
    if left is None:
        return right
    if right is None:
        return left
    x1, y1 = left
    x2, y2 = right
    if x1 == x2 and (y1 != y2 or y1 == 0):
        return None
    if left == right:
        slope = (3 * x1 * x1) * inverse(2 * y1 % FIELD_PRIME) % FIELD_PRIME
    else:
        slope = (y2 - y1) * inverse((x2 - x1) % FIELD_PRIME) % FIELD_PRIME
    x3 = (slope * slope - x1 - x2) % FIELD_PRIME
    y3 = (slope * (x1 - x3) - y1) % FIELD_PRIME
    return x3, y3


def point_multiply(scalar: int) -> tuple[int, int] | None:
    result = None
    addend: tuple[int, int] | None = GENERATOR
    while scalar:
        if scalar & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        scalar >>= 1
    return result


def parse_public_key(value: bytes) -> tuple[int, int]:
    x = int.from_bytes(value[1:], "big")
    y = pow((pow(x, 3, FIELD_PRIME) + 7) % FIELD_PRIME, (FIELD_PRIME + 1) // 4, FIELD_PRIME)
    if y & 1 != value[0] & 1:
        y = FIELD_PRIME - y
    return x, y


def serialize_public_key(point: tuple[int, int]) -> bytes:
    x, y = point
    return bytes([2 + (y & 1)]) + x.to_bytes(32, "big")


def derive_child(public_key: bytes, chain_code: bytes, index: int) -> tuple[bytes, bytes]:
    digest = hmac.new(
        chain_code,
        public_key + index.to_bytes(4, "big"),
        hashlib.sha512,
    ).digest()
    scalar = int.from_bytes(digest[:32], "big")
    if not 0 < scalar < CURVE_ORDER:
        raise ValueError("invalid BIP32 child scalar")
    point = point_add(parse_public_key(public_key), point_multiply(scalar))
    if point is None:
        raise ValueError("invalid BIP32 child point")
    return serialize_public_key(point), digest[32:]


def decode_ypub(value: str) -> tuple[bytes, bytes]:
    decoded = base58_decode(value)
    valid_checksum = len(decoded) == 82 and sha256(sha256(decoded[:-4]))[:4] == decoded[-4:]
    if not valid_checksum or decoded[:4] != bytes.fromhex("049d7cb2"):
        raise ValueError("invalid mainnet ypub")
    payload = decoded[:-4]
    return payload[45:78], payload[13:45]


def p2sh_p2wpkh_address(public_key: bytes) -> str:
    key_hash = ripemd160(sha256(public_key))
    redeem_script = b"\x00\x14" + key_hash
    return base58check(b"\x05" + ripemd160(sha256(redeem_script)))


def bitcoin_address_transactions(address: str) -> list[dict[str, Any]]:
    transactions = get_json(f"{MEMPOOL_API}/address/{address}/txs/mempool")
    after_txid: str | None = None
    while True:
        url = f"{MEMPOOL_API}/address/{address}/txs/chain"
        if after_txid:
            url += f"/{after_txid}"
        page = get_json(url)
        transactions.extend(page)
        if len(page) < 25:
            return transactions
        after_txid = page[-1]["txid"]
        time.sleep(0.15)


BITCOIN_COLUMNS = [
    "timestamp_utc",
    "transaction_hash",
    "confirmed",
    "block_height",
    "block_hash",
    "wallet_input_addresses",
    "wallet_output_addresses",
    "wallet_input_sats",
    "wallet_output_sats",
    "wallet_net_sats",
    "wallet_net_btc",
    "transaction_fee_sats",
    "transaction_fee_btc",
    "input_count",
    "output_count",
    "size_bytes",
    "weight",
    "version",
    "locktime",
    "source_url",
]


def fetch_bitcoin_table(ypub: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    account_key, account_chain = decode_ypub(ypub)
    scanned_addresses: list[str] = []
    used_addresses: list[str] = []
    transactions_by_id: dict[str, dict[str, Any]] = {}

    for branch in (0, 1):
        branch_key, branch_chain = derive_child(account_key, account_chain, branch)
        consecutive_unused = 0
        index = 0
        while consecutive_unused < GAP_LIMIT:
            child_key, _ = derive_child(branch_key, branch_chain, index)
            address = p2sh_p2wpkh_address(child_key)
            scanned_addresses.append(address)
            summary = get_json(f"{MEMPOOL_API}/address/{address}")
            transaction_count = (
                summary["chain_stats"]["tx_count"] + summary["mempool_stats"]["tx_count"]
            )
            if transaction_count:
                used_addresses.append(address)
                consecutive_unused = 0
                for transaction in bitcoin_address_transactions(address):
                    transactions_by_id[transaction["txid"]] = transaction
            else:
                consecutive_unused += 1
            index += 1
            time.sleep(0.12)

    wallet_addresses = set(scanned_addresses)
    rows: list[dict[str, Any]] = []
    for txid in sorted(transactions_by_id):
        transaction = get_json(f"{MEMPOOL_API}/tx/{txid}")
        inputs = [item.get("prevout") or {} for item in transaction.get("vin", [])]
        outputs = transaction.get("vout", [])
        wallet_inputs = [
            item for item in inputs if item.get("scriptpubkey_address") in wallet_addresses
        ]
        wallet_outputs = [
            item for item in outputs if item.get("scriptpubkey_address") in wallet_addresses
        ]
        input_sats = sum(int(item.get("value", 0)) for item in wallet_inputs)
        output_sats = sum(int(item.get("value", 0)) for item in wallet_outputs)
        net_sats = output_sats - input_sats
        status = transaction.get("status") or {}
        block_time = status.get("block_time")
        timestamp = (
            datetime.fromtimestamp(block_time, timezone.utc).isoformat().replace("+00:00", "Z")
            if block_time is not None
            else ""
        )
        fee_sats = transaction.get("fee", "")
        rows.append(
            {
                "timestamp_utc": timestamp,
                "transaction_hash": txid,
                "confirmed": status.get("confirmed", False),
                "block_height": status.get("block_height", ""),
                "block_hash": status.get("block_hash", ""),
                "wallet_input_addresses": ";".join(
                    sorted({item["scriptpubkey_address"] for item in wallet_inputs})
                ),
                "wallet_output_addresses": ";".join(
                    sorted({item["scriptpubkey_address"] for item in wallet_outputs})
                ),
                "wallet_input_sats": input_sats,
                "wallet_output_sats": output_sats,
                "wallet_net_sats": net_sats,
                "wallet_net_btc": format_units(net_sats, 8),
                "transaction_fee_sats": fee_sats,
                "transaction_fee_btc": format_units(fee_sats, 8),
                "input_count": len(transaction.get("vin", [])),
                "output_count": len(outputs),
                "size_bytes": transaction.get("size", ""),
                "weight": transaction.get("weight", ""),
                "version": transaction.get("version", ""),
                "locktime": transaction.get("locktime", ""),
                "source_url": f"{MEMPOOL_SITE}/tx/{txid}",
            }
        )
    rows.sort(key=lambda row: (row["timestamp_utc"], row["transaction_hash"]))
    return rows, {
        "gap_limit": GAP_LIMIT,
        "addresses_scanned": len(scanned_addresses),
        "used_addresses": used_addresses,
        "table_rows": len(rows),
    }


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ethereum_wallet, bitcoin_wallet = load_wallets()
    print("Fetching Ethereum transaction table", flush=True)
    ethereum_rows, ethereum_counts = fetch_ethereum_table(ethereum_wallet)
    write_csv(ETHEREUM_CSV, ETHEREUM_COLUMNS, ethereum_rows)

    print("Fetching Bitcoin transaction table", flush=True)
    bitcoin_rows, bitcoin_counts = fetch_bitcoin_table(bitcoin_wallet)
    write_csv(BITCOIN_CSV, BITCOIN_COLUMNS, bitcoin_rows)

    sources = {
        "generated_at": utc_now(),
        "contains_tax_calculations": False,
        "ethereum": {
            "wallet": ethereum_wallet,
            "source": BLOCKSCOUT_API,
            "table": str(ETHEREUM_CSV),
            **ethereum_counts,
        },
        "bitcoin": {
            "wallet_type": "ypub (BIP49 P2SH-P2WPKH)",
            "wallet_fingerprint": hashlib.sha256(bitcoin_wallet.encode("ascii")).hexdigest()[:16],
            "source": MEMPOOL_API,
            "table": str(BITCOIN_CSV),
            **bitcoin_counts,
        },
    }
    SOURCES_FILE.write_text(
        json.dumps(sources, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(ethereum_rows)} Ethereum rows and {len(bitcoin_rows)} Bitcoin rows")


if __name__ == "__main__":
    main()
