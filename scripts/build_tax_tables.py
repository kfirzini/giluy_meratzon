#!/usr/bin/env python3
"""Build estimated BTC/ETH FIFO tax workpapers in NIS.

Blockchain transfers do not contain the fiat consideration paid or received.
When an override is not supplied, this script estimates the NIS value from the
nearest Coinbase one-minute USD close and the daily Frankfurter USD/ILS rate.
The estimates are cached so a rebuild is reproducible and auditable.
"""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any


getcontext().prec = 40

SUMMARY_DIRECTORY = Path("transactions_data/summaries")
TAX_DIRECTORY = Path("transactions_data/tax")
ALL_TRANSACTIONS_CSV = SUMMARY_DIRECTORY / "all_transactions.csv"
OVERRIDES_CSV = TAX_DIRECTORY / "nis_value_overrides.csv"
PRICE_CACHE_CSV = TAX_DIRECTORY / "historical_nis_prices.csv"
FIFO_ALLOCATIONS_CSV = TAX_DIRECTORY / "fifo_allocations.csv"
TRANSACTION_TAX_CSV = TAX_DIRECTORY / "tax_by_transaction.csv"
YEARLY_TAX_CSV = TAX_DIRECTORY / "tax_by_year.csv"

TAX_RATE = Decimal("0.25")
SUPPORTED_COINS = {"BTC", "ETH"}
ECONOMIC_TYPES = {"buying", "selling"}

OVERRIDE_COLUMNS = [
    "date",
    "type",
    "coin_type",
    "transaction_hash",
    "gross_value_nis",
    "sale_expenses_nis",
    "evidence_or_notes",
]

PRICE_COLUMNS = [
    "transaction_hash",
    "transaction_date_utc",
    "coin_type",
    "crypto_price_timestamp_utc",
    "price_usd",
    "usd_ils_rate",
    "usd_ils_rate_date",
    "price_nis",
    "crypto_source_url",
    "fx_source_url",
]

ALLOCATION_COLUMNS = [
    "tax_year",
    "sale_date",
    "coin_type",
    "sale_transaction_hash",
    "purchase_date",
    "purchase_transaction_hash",
    "quantity_matched",
    "purchase_unit_price_nis",
    "purchase_cost_nis",
    "sale_unit_price_nis",
    "gross_sale_value_nis",
    "sale_expenses_nis",
    "net_sale_proceeds_nis",
    "gain_loss_nis",
]

TRANSACTION_TAX_COLUMNS = [
    "tax_year",
    "sale_date",
    "coin_type",
    "sale_transaction_hash",
    "quantity_sold",
    "gross_sale_value_nis",
    "sale_expenses_nis",
    "net_sale_proceeds_nis",
    "fifo_purchase_lots",
    "fifo_cost_basis_nis",
    "gain_loss_nis",
    "tax_before_annual_offsets_nis",
    "nis_value_method",
    "source_url",
]

YEARLY_TAX_COLUMNS = [
    "tax_year",
    "coin_type",
    "sale_transactions",
    "quantity_sold",
    "net_sale_proceeds_nis",
    "fifo_cost_basis_nis",
    "gain_loss_nis",
    "taxable_annual_gain_nis",
    "tax_owed_25_percent_nis",
]


@dataclass
class Lot:
    date: str
    transaction_hash: str
    quantity_remaining: Decimal
    unit_cost_nis: Decimal


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def nis_text(value: Decimal) -> str:
    return format(round_nis(value), "f")


def round_nis(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def price_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP), "f")


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def iso_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "giluy-meratzon-tax-workpaper/1.0",
        },
    )
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception as error:  # retry transient HTTP and network errors
            last_error = error
            if attempt < 3:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def coinbase_price(coin: str, timestamp: datetime) -> tuple[Decimal, str, str]:
    minute = timestamp.replace(second=0, microsecond=0)
    parameters = urllib.parse.urlencode(
        {
            "start": iso_timestamp(minute - timedelta(minutes=30)),
            "end": iso_timestamp(minute + timedelta(minutes=2)),
            "granularity": 60,
        }
    )
    url = f"https://api.exchange.coinbase.com/products/{coin}-USD/candles?{parameters}"
    candles = http_json(url)
    if not isinstance(candles, list) or not candles:
        raise ValueError(f"Coinbase returned no {coin}-USD candles near {iso_timestamp(timestamp)}")

    target_epoch = int(minute.timestamp())
    at_or_before = [candle for candle in candles if int(candle[0]) <= target_epoch]
    candidates = at_or_before or candles
    candle = min(candidates, key=lambda item: abs(int(item[0]) - target_epoch))
    candle_time = datetime.fromtimestamp(int(candle[0]), tz=timezone.utc)
    close_usd = Decimal(str(candle[4]))
    return close_usd, iso_timestamp(candle_time), url


def usd_ils_rate(date: str) -> tuple[Decimal, str, str]:
    url = f"https://api.frankfurter.app/{date}?from=USD&to=ILS"
    payload = http_json(url)
    return Decimal(str(payload["rates"]["ILS"])), str(payload["date"]), url


def relevant_transactions(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row["coin_type"] in SUPPORTED_COINS
        and row["type"] in ECONOMIC_TYPES
        and row["status"] in {"ok", "confirmed"}
        and row["amount"] != ""
        and Decimal(row["amount"]) > 0
    ]


def ensure_override_template(transactions: list[dict[str, str]]) -> None:
    existing: dict[tuple[str, str], dict[str, str]] = {}
    if OVERRIDES_CSV.exists():
        for row in read_csv(OVERRIDES_CSV):
            existing[(row["transaction_hash"].lower(), row["coin_type"])] = row

    output: list[dict[str, str]] = []
    for transaction in transactions:
        key = (transaction["transaction_hash"].lower(), transaction["coin_type"])
        prior = existing.get(key, {})
        output.append(
            {
                "date": transaction["date"],
                "type": transaction["type"],
                "coin_type": transaction["coin_type"],
                "transaction_hash": transaction["transaction_hash"],
                "gross_value_nis": prior.get("gross_value_nis", ""),
                "sale_expenses_nis": prior.get("sale_expenses_nis", ""),
                "evidence_or_notes": prior.get("evidence_or_notes", ""),
            }
        )
    write_csv(OVERRIDES_CSV, OVERRIDE_COLUMNS, output)


def load_overrides() -> dict[tuple[str, str], dict[str, str]]:
    return {
        (row["transaction_hash"].lower(), row["coin_type"]): row
        for row in read_csv(OVERRIDES_CSV)
    }


def load_price_cache() -> dict[tuple[str, str], dict[str, str]]:
    if not PRICE_CACHE_CSV.exists():
        return {}
    return {
        (row["transaction_hash"].lower(), row["coin_type"]): row
        for row in read_csv(PRICE_CACHE_CSV)
    }


def update_price_cache(
    transactions: list[dict[str, str]],
    overrides: dict[tuple[str, str], dict[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    cache = load_price_cache()
    fx_cache: dict[str, tuple[Decimal, str, str]] = {}

    for transaction in transactions:
        key = (transaction["transaction_hash"].lower(), transaction["coin_type"])
        override = overrides[key]
        needs_market_value = override["gross_value_nis"] == ""
        needs_market_expense = (
            transaction["type"] == "selling"
            and transaction["fee"] != ""
            and override["sale_expenses_nis"] == ""
        )
        if not (needs_market_value or needs_market_expense) or key in cache:
            continue

        timestamp = parse_timestamp(transaction["date"])
        price_usd, price_timestamp, crypto_url = coinbase_price(
            transaction["coin_type"], timestamp
        )
        date = transaction["date"][:10]
        if date not in fx_cache:
            fx_cache[date] = usd_ils_rate(date)
        fx_rate, fx_date, fx_url = fx_cache[date]
        price_nis = price_usd * fx_rate
        cache[key] = {
            "transaction_hash": transaction["transaction_hash"],
            "transaction_date_utc": transaction["date"],
            "coin_type": transaction["coin_type"],
            "crypto_price_timestamp_utc": price_timestamp,
            "price_usd": price_text(price_usd),
            "usd_ils_rate": price_text(fx_rate),
            "usd_ils_rate_date": fx_date,
            "price_nis": price_text(price_nis),
            "crypto_source_url": crypto_url,
            "fx_source_url": fx_url,
        }
        time.sleep(0.12)

    ordered = sorted(
        cache.values(),
        key=lambda row: (
            row["transaction_date_utc"],
            row["coin_type"],
            row["transaction_hash"].lower(),
        ),
    )
    write_csv(PRICE_CACHE_CSV, PRICE_COLUMNS, ordered)
    return cache


def transaction_values(
    transaction: dict[str, str],
    override: dict[str, str],
    price: dict[str, str] | None,
) -> tuple[Decimal, Decimal, Decimal, str]:
    amount = Decimal(transaction["amount"])
    if override["gross_value_nis"] != "":
        gross_value = Decimal(override["gross_value_nis"])
        value_method = "actual NIS override"
    else:
        if price is None:
            raise ValueError(f"missing market price for {transaction['transaction_hash']}")
        gross_value = amount * Decimal(price["price_nis"])
        value_method = "market estimate: Coinbase USD x Frankfurter USD/ILS"

    sale_expenses = Decimal(override["sale_expenses_nis"] or "0")
    if (
        transaction["type"] == "selling"
        and override["sale_expenses_nis"] == ""
        and transaction["fee"] != ""
    ):
        if price is None:
            raise ValueError(f"missing fee price for {transaction['transaction_hash']}")
        sale_expenses = Decimal(transaction["fee"]) * Decimal(price["price_nis"])

    return gross_value, sale_expenses, gross_value / amount, value_method


def build_fifo_tables(
    transactions: list[dict[str, str]],
    overrides: dict[tuple[str, str], dict[str, str]],
    prices: dict[tuple[str, str], dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    inventories: dict[str, deque[Lot]] = defaultdict(deque)
    allocations: list[dict[str, str]] = []
    sales: list[dict[str, str]] = []

    for transaction in transactions:
        key = (transaction["transaction_hash"].lower(), transaction["coin_type"])
        gross_value, sale_expenses, unit_price, value_method = transaction_values(
            transaction, overrides[key], prices.get(key)
        )
        quantity = Decimal(transaction["amount"])
        coin = transaction["coin_type"]

        if transaction["type"] == "buying":
            inventories[coin].append(
                Lot(
                    date=transaction["date"],
                    transaction_hash=transaction["transaction_hash"],
                    quantity_remaining=quantity,
                    unit_cost_nis=unit_price,
                )
            )
            continue

        remaining = quantity
        sale_allocations: list[dict[str, str]] = []
        precise_fifo_cost = Decimal("0")
        while remaining > 0:
            if not inventories[coin]:
                raise ValueError(
                    f"insufficient {coin} FIFO inventory for sale {transaction['transaction_hash']}"
                )
            lot = inventories[coin][0]
            matched = min(remaining, lot.quantity_remaining)
            ratio = matched / quantity
            allocated_gross = gross_value * ratio
            allocated_expenses = sale_expenses * ratio
            allocated_cost = matched * lot.unit_cost_nis
            precise_fifo_cost += allocated_cost
            displayed_allocated_gross = round_nis(allocated_gross)
            displayed_allocated_expenses = round_nis(allocated_expenses)
            displayed_allocated_net = (
                displayed_allocated_gross - displayed_allocated_expenses
            )
            displayed_allocated_cost = round_nis(allocated_cost)
            displayed_allocated_gain = displayed_allocated_net - displayed_allocated_cost

            allocation = {
                "tax_year": transaction["date"][:4],
                "sale_date": transaction["date"],
                "coin_type": coin,
                "sale_transaction_hash": transaction["transaction_hash"],
                "purchase_date": lot.date,
                "purchase_transaction_hash": lot.transaction_hash,
                "quantity_matched": decimal_text(matched),
                "purchase_unit_price_nis": price_text(lot.unit_cost_nis),
                "purchase_cost_nis": nis_text(displayed_allocated_cost),
                "sale_unit_price_nis": price_text(unit_price),
                "gross_sale_value_nis": nis_text(displayed_allocated_gross),
                "sale_expenses_nis": nis_text(displayed_allocated_expenses),
                "net_sale_proceeds_nis": nis_text(displayed_allocated_net),
                "gain_loss_nis": nis_text(displayed_allocated_gain),
            }
            allocations.append(allocation)
            sale_allocations.append(allocation)

            lot.quantity_remaining -= matched
            remaining -= matched
            if lot.quantity_remaining == 0:
                inventories[coin].popleft()

        displayed_gross = round_nis(gross_value)
        displayed_expenses = round_nis(sale_expenses)
        displayed_net = displayed_gross - displayed_expenses
        displayed_fifo_cost = round_nis(precise_fifo_cost)
        displayed_gain = displayed_net - displayed_fifo_cost

        # Make the supporting allocation rows add exactly to the displayed
        # transaction row after rounding to agorot. Any rounding residual is
        # placed on the final FIFO allocation for that sale.
        prior_allocations = sale_allocations[:-1]
        final_allocation = sale_allocations[-1]
        final_gross = displayed_gross - sum(
            (Decimal(row["gross_sale_value_nis"]) for row in prior_allocations), Decimal()
        )
        final_expenses = displayed_expenses - sum(
            (Decimal(row["sale_expenses_nis"]) for row in prior_allocations), Decimal()
        )
        final_cost = displayed_fifo_cost - sum(
            (Decimal(row["purchase_cost_nis"]) for row in prior_allocations), Decimal()
        )
        final_allocation["gross_sale_value_nis"] = nis_text(final_gross)
        final_allocation["sale_expenses_nis"] = nis_text(final_expenses)
        final_allocation["net_sale_proceeds_nis"] = nis_text(final_gross - final_expenses)
        final_allocation["purchase_cost_nis"] = nis_text(final_cost)
        final_allocation["gain_loss_nis"] = nis_text(
            final_gross - final_expenses - final_cost
        )

        lots_text = "; ".join(
            f"{row['purchase_date'][:10]}: {row['quantity_matched']} {coin}"
            for row in sale_allocations
        )
        tax_before_offsets = max(displayed_gain, Decimal("0")) * TAX_RATE
        sales.append(
            {
                "tax_year": transaction["date"][:4],
                "sale_date": transaction["date"],
                "coin_type": coin,
                "sale_transaction_hash": transaction["transaction_hash"],
                "quantity_sold": decimal_text(quantity),
                "gross_sale_value_nis": nis_text(displayed_gross),
                "sale_expenses_nis": nis_text(displayed_expenses),
                "net_sale_proceeds_nis": nis_text(displayed_net),
                "fifo_purchase_lots": lots_text,
                "fifo_cost_basis_nis": nis_text(displayed_fifo_cost),
                "gain_loss_nis": nis_text(displayed_gain),
                "tax_before_annual_offsets_nis": nis_text(tax_before_offsets),
                "nis_value_method": value_method,
                "source_url": transaction["source_url"],
            }
        )

    return allocations, sales


def build_yearly_table(sales: list[dict[str, str]]) -> list[dict[str, str | int]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for sale in sales:
        grouped[(sale["tax_year"], sale["coin_type"])].append(sale)

    output: list[dict[str, str | int]] = []
    sale_years = sorted(int(sale["tax_year"]) for sale in sales)
    years = [str(year) for year in range(min(sale_years), max(sale_years) + 1)]
    for year in years:
        year_sales = [sale for sale in sales if sale["tax_year"] == year]
        for coin in sorted({sale["coin_type"] for sale in year_sales}):
            coin_sales = grouped[(year, coin)]
            net_proceeds = sum(
                (Decimal(row["net_sale_proceeds_nis"]) for row in coin_sales), Decimal()
            )
            fifo_cost = sum(
                (Decimal(row["fifo_cost_basis_nis"]) for row in coin_sales), Decimal()
            )
            gain = net_proceeds - fifo_cost
            taxable = max(gain, Decimal("0"))
            output.append(
                {
                    "tax_year": year,
                    "coin_type": coin,
                    "sale_transactions": len(coin_sales),
                    "quantity_sold": decimal_text(
                        sum((Decimal(row["quantity_sold"]) for row in coin_sales), Decimal())
                    ),
                    "net_sale_proceeds_nis": nis_text(net_proceeds),
                    "fifo_cost_basis_nis": nis_text(fifo_cost),
                    "gain_loss_nis": nis_text(gain),
                    "taxable_annual_gain_nis": nis_text(taxable),
                    "tax_owed_25_percent_nis": nis_text(taxable * TAX_RATE),
                }
            )

        total_net_proceeds = sum(
            (Decimal(row["net_sale_proceeds_nis"]) for row in year_sales), Decimal()
        )
        total_fifo_cost = sum(
            (Decimal(row["fifo_cost_basis_nis"]) for row in year_sales), Decimal()
        )
        total_gain = total_net_proceeds - total_fifo_cost
        total_taxable = max(total_gain, Decimal("0"))
        output.append(
            {
                "tax_year": year,
                "coin_type": "ALL",
                "sale_transactions": len(year_sales),
                "quantity_sold": "",
                "net_sale_proceeds_nis": nis_text(total_net_proceeds),
                "fifo_cost_basis_nis": nis_text(total_fifo_cost),
                "gain_loss_nis": nis_text(total_gain),
                "taxable_annual_gain_nis": nis_text(total_taxable),
                "tax_owed_25_percent_nis": nis_text(total_taxable * TAX_RATE),
            }
        )
    return output


def validate_outputs(
    transactions: list[dict[str, str]],
    allocations: list[dict[str, str]],
    sales: list[dict[str, str]],
    yearly: list[dict[str, str | int]],
) -> None:
    source_sales = [row for row in transactions if row["type"] == "selling"]
    if len(source_sales) != len(sales):
        raise ValueError("not every BTC/ETH sale produced one transaction tax row")
    allocated_by_sale: dict[str, Decimal] = defaultdict(Decimal)
    for row in allocations:
        allocated_by_sale[row["sale_transaction_hash"].lower()] += Decimal(
            row["quantity_matched"]
        )
    for sale in sales:
        sale_hash = sale["sale_transaction_hash"].lower()
        if allocated_by_sale[sale_hash] != Decimal(sale["quantity_sold"]):
            raise ValueError(f"FIFO allocations do not match sale {sale['sale_transaction_hash']}")
        if (
            Decimal(sale["net_sale_proceeds_nis"])
            - Decimal(sale["fifo_cost_basis_nis"])
            != Decimal(sale["gain_loss_nis"])
        ):
            raise ValueError(f"displayed sale arithmetic does not tie for {sale_hash}")
        sale_allocations = [
            row for row in allocations if row["sale_transaction_hash"].lower() == sale_hash
        ]
        for field in (
            "gross_sale_value_nis",
            "sale_expenses_nis",
            "net_sale_proceeds_nis",
            "gain_loss_nis",
        ):
            if sum((Decimal(row[field]) for row in sale_allocations), Decimal()) != Decimal(
                sale[field]
            ):
                raise ValueError(f"allocation {field} does not tie for {sale_hash}")
        if sum(
            (Decimal(row["purchase_cost_nis"]) for row in sale_allocations), Decimal()
        ) != Decimal(sale["fifo_cost_basis_nis"]):
            raise ValueError(f"allocation cost does not tie for {sale_hash}")
    all_rows = [row for row in yearly if row["coin_type"] == "ALL"]
    first_year = min(int(sale["tax_year"]) for sale in sales)
    last_year = max(int(sale["tax_year"]) for sale in sales)
    if len(all_rows) != last_year - first_year + 1:
        raise ValueError("yearly table is missing a contiguous ALL row")
    for row in yearly:
        if (
            Decimal(str(row["net_sale_proceeds_nis"]))
            - Decimal(str(row["fifo_cost_basis_nis"]))
            != Decimal(str(row["gain_loss_nis"]))
        ):
            raise ValueError(
                f"displayed annual arithmetic does not tie for "
                f"{row['tax_year']} {row['coin_type']}"
            )


def main() -> None:
    if not ALL_TRANSACTIONS_CSV.exists():
        raise SystemExit(
            f"{ALL_TRANSACTIONS_CSV} does not exist; run scripts/build_transaction_summaries.py first"
        )
    transactions = relevant_transactions(read_csv(ALL_TRANSACTIONS_CSV))
    transactions.sort(
        key=lambda row: (row["date"], row["coin_type"], row["transaction_hash"])
    )
    ensure_override_template(transactions)
    overrides = load_overrides()
    prices = update_price_cache(transactions, overrides)
    allocations, sales = build_fifo_tables(transactions, overrides, prices)
    yearly = build_yearly_table(sales)
    validate_outputs(transactions, allocations, sales, yearly)
    write_csv(FIFO_ALLOCATIONS_CSV, ALLOCATION_COLUMNS, allocations)
    write_csv(TRANSACTION_TAX_CSV, TRANSACTION_TAX_COLUMNS, sales)
    write_csv(YEARLY_TAX_CSV, YEARLY_TAX_COLUMNS, yearly)
    print(
        f"Wrote {len(allocations)} FIFO allocations, {len(sales)} sale rows, "
        f"and {len(yearly)} yearly rows"
    )


if __name__ == "__main__":
    main()
