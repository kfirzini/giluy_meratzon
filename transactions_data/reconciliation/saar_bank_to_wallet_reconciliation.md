# Bank payments to Saar matched to coin receipts in owned wallets

## Proposed result

| Bank payment | Proposed wallet receipts | Confidence |
|---|---|---|
| 4 Jun + 12 Jun 2017: NIS 6,000 each | Two Saar-wallet bundles totaling 13.652 ETH | Medium |
| 26 Jul 2017: NIS 18,000 | 15.90946423 ETH in four direct Bitstamp payouts | High |
| 3 Dec 2017: NIS 2,760 | 0.643 ETH in two direct Bitstamp payouts one day before payment | Low / partial |
| 10 Dec 2017: NIS 2,300 | 0.791 ETH from Saar's identified wallet on 14 Dec | Medium |
| 12 Dec 2017: NIS 3,000 | 0.0608089 BTC from Bitstamp on 14 Dec | Medium-high |

If all proposed matches are accepted, the six bank payments totaling NIS
38,060 correspond to the table's wallet receipts totaling **30.99546423 ETH
and 0.0608089 BTC**. Token receipts are intentionally excluded.

## June payments: two interchangeable NIS 6,000 assignments

The bank has two identical NIS 6,000 payments, so the evidence cannot determine
which date belongs to which source-wallet bundle. Because both payments have the
same amount, that ambiguity does not change the proposed NIS 6,000 cost of each
bundle.

BTC/ETH rows from possible Saar wallet `0xC7C1...`:

- 12 Jul: 6.614 ETH

BTC/ETH rows from Saar wallet `0xc3B0...`:

- 12 Jul: 0.005 ETH test and 7.033 ETH

The ETH had an estimated receipt-date value of NIS 9,759.37 across the two
bundles. The remaining difference may reflect excluded token receipts, price
movement, or the private terms of the purchase. The NIS 6,000 bundle costs have
therefore not been allocated to individual ETH transactions.

## 26 July payment: strongest match

The NIS 18,000 payment matches four Bitstamp withdrawals received exactly in
the owned wallet:

| Receipt | Amount | Receipt-date estimate | Provisional payment allocation |
|---|---:|---:|---:|
| 20 Aug 14:42 UTC | 0.12421232 ETH | NIS 132.49 | NIS 138.35 |
| 20 Aug 15:14 UTC | 5 ETH | NIS 5,321.79 | NIS 5,557.24 |
| 4 Sep 07:24 UTC | 3.94414191 ETH | NIS 4,771.42 | NIS 4,982.52 |
| 10 Sep 08:06 UTC | 6.84111 ETH | NIS 7,011.67 | NIS 7,321.89 |
| **Total** | **15.90946423 ETH** | **NIS 17,237.37** | **NIS 18,000.00** |

Each Bitstamp line and wallet receipt has the same exact amount and a timestamp
within 13 seconds to 3 minutes. The provisional NIS allocation distributes the
actual bank payment proportionally using receipt-date market values.

## December payments

### 3 December: unresolved or partial

The wallet received 0.043 ETH and 0.600 ETH directly from Bitstamp on 2
December, then the NIS 2,760 payment was made the next day. The exact
exchange-to-wallet evidence and timing are strong, but their estimated combined
value was only NIS 1,037.63. This match should remain low confidence unless
there was another coin delivery, an agreed non-market price, or other evidence.

The CSV contains a provisional pro-rata payment allocation of NIS 184.76 and
NIS 2,575.24. These values should not be entered into the tax override table
until the mismatch is resolved or consciously accepted.

### 10 and 12 December: coordinated ETH and BTC delivery

On 14 December, two owned wallets received:

- 0.791 ETH from Saar's identified wallet at 10:55:16 UTC.
- 0.0608089 BTC from Bitstamp at 10:55:27 UTC.

The eleven-second separation strongly suggests a coordinated delivery. Their
estimated values were NIS 2,071.19 and NIS 3,639.24. Assigning the NIS 2,300
payment to the ETH and the NIS 3,000 payment to the BTC produces the closest
individual value match. Combined, NIS 5,300 was paid for assets estimated at
NIS 5,710.43, a 7.7% difference.

## Evidence boundary

Blockchain receipt dates, amounts, addresses, and hashes are proven facts. The
Bitstamp-to-wallet links with exact amounts and near-identical times are also
very strong. Assigning a particular bank payment is still a reconciliation
judgment because neither the bank statement nor the blockchain contains a
shared purchase identifier.

The detailed transaction-level mapping and transaction hashes are in
`saar_bank_to_wallet_matches.csv`. No tax override was changed by this work.
