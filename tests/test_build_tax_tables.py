import importlib.util
import sys
import unittest
from decimal import Decimal
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "build_tax_tables.py"
SPEC = importlib.util.spec_from_file_location("build_tax_tables", MODULE_PATH)
tax = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = tax
SPEC.loader.exec_module(tax)


def transaction(date, kind, amount, tx_hash):
    return {
        "date": date,
        "type": kind,
        "amount": amount,
        "coin_type": "ETH",
        "fee": "",
        "transaction_hash": tx_hash,
        "source_url": f"https://example.test/{tx_hash}",
    }


class TaxTableTests(unittest.TestCase):
    def test_fifo_sale_consumes_oldest_lots_and_ties_to_annual_tax(self):
        transactions = [
            transaction("2020-01-01T00:00:00Z", "buying", "1", "buy-1"),
            transaction("2020-02-01T00:00:00Z", "buying", "2", "buy-2"),
            transaction("2021-01-01T00:00:00Z", "selling", "1.5", "sell-1"),
        ]
        overrides = {
            ("buy-1", "ETH"): {
                "gross_value_nis": "100",
                "sale_expenses_nis": "",
            },
            ("buy-2", "ETH"): {
                "gross_value_nis": "400",
                "sale_expenses_nis": "",
            },
            ("sell-1", "ETH"): {
                "gross_value_nis": "600",
                "sale_expenses_nis": "",
            },
        }

        allocations, sales = tax.build_fifo_tables(transactions, overrides, {})
        yearly = tax.build_yearly_table(sales)

        self.assertEqual([row["quantity_matched"] for row in allocations], ["1", "0.5"])
        self.assertEqual(sales[0]["fifo_cost_basis_nis"], "200.00")
        self.assertEqual(sales[0]["gain_loss_nis"], "400.00")
        self.assertEqual(sales[0]["tax_before_annual_offsets_nis"], "100.00")
        self.assertEqual(yearly[-1]["tax_owed_25_percent_nis"], "100.00")

    def test_yearly_tax_nets_transaction_losses(self):
        sales = [
            {
                "tax_year": "2024",
                "coin_type": "ETH",
                "quantity_sold": "1",
                "net_sale_proceeds_nis": "200.00",
                "fifo_cost_basis_nis": "100.00",
                "gain_loss_nis": "100.00",
            },
            {
                "tax_year": "2024",
                "coin_type": "ETH",
                "quantity_sold": "1",
                "net_sale_proceeds_nis": "60.00",
                "fifo_cost_basis_nis": "100.00",
                "gain_loss_nis": "-40.00",
            },
        ]

        yearly = tax.build_yearly_table(sales)
        all_row = next(row for row in yearly if row["coin_type"] == "ALL")

        self.assertEqual(Decimal(all_row["gain_loss_nis"]), Decimal("60.00"))
        self.assertEqual(Decimal(all_row["tax_owed_25_percent_nis"]), Decimal("15.00"))


if __name__ == "__main__":
    unittest.main()
