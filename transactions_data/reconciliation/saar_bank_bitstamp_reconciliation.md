# Reconciliation of bank payments to Saar and Saar's Bitstamp history

## Result

Seven Bitstamp withdrawal rows can be matched exactly to receipts in the
configured owned wallets. Those links use the same coin, the full exact amount,
and a blockchain timestamp between 13 seconds and 7 minutes after the Bitstamp
withdrawal. They are recorded in `saar_bitstamp_exact_wallet_matches.csv`.

Connecting a bank payment to a particular withdrawal is necessarily an
inference: the bank rows contain no Bitstamp identifier, and the Bitstamp export
contains no bank sender or purchase-owner field. The most defensible allocations
are below.

## Proposed bank-payment allocations

### High confidence: 26 July 2017, NIS 18,000 (reference 16337)

This payment is a strong match to four Bitstamp withdrawals that arrived
exactly in an owned wallet:

| Bitstamp withdrawal (UTC) | Amount received | Blockchain delay | Estimated market value (NIS) |
|---|---:|---:|---:|
| 20 Aug 2017 14:42:05 | 0.12421232 ETH | 13 seconds | 132.49 |
| 20 Aug 2017 15:13:55 | 5 ETH | 19 seconds | 5,321.79 |
| 4 Sep 2017 07:21 | 3.94414191 ETH | 3m 7s | 4,771.42 |
| 10 Sep 2017 08:06 | 6.84111000 ETH | 21 seconds | 7,011.67 |
| **Total** | **15.90946423 ETH** | | **17,237.37** |

The estimated receipt-date value is only NIS 762.63 (4.2%) below the NIS
18,000 payment. This is the strongest bank-to-crypto grouping in the data.
The USD 6,000 Bitstamp deposit on 18 August is useful funding context, but is
not itself an amount match: it was worth about NIS 21,739 at the nearby
USD/ILS rate.

### Medium confidence, but ambiguous: one of the two NIS 6,000 payments

Candidate bank rows:

- 4 June 2017, NIS 6,000, reference 2000
- 12 June 2017, NIS 6,000, reference 31971

Candidate Bitstamp chain:

- 10 July 2017: USD 1,680 deposit
- 12 July 2017: 0.70532 BTC withdrawal

USD 1,680 at the 12 July reference exchange rate of 3.5531 equals NIS
5,969.21, just NIS 30.79 (0.5%) below either payment. This is a strong amount
match, and the later bank row is closer in time, but the two payments have the
same amount so the records cannot identify which one funded this deposit.
The 0.70532 BTC withdrawal was not found in the currently configured owned BTC
wallet history, so it should not be claimed as a receipt by the owner without
an additional wallet address or other evidence.

There is a separate possible explanation for both June payments: on 12 July,
13.647 ETH arrived in an owned wallet from addresses noted as possible Saar
wallets (6.614 ETH and 7.033 ETH), followed on 22-23 July by EOS and BNT from
the same addresses. These are not exact matches to a Bitstamp row and therefore
remain supporting context, not reconciled Bitstamp withdrawals.

### Medium confidence as a combined December delivery

Candidate bank rows:

- 10 December 2017, NIS 2,300, reference 135627
- 12 December 2017, NIS 3,000, reference 38809
- Combined payment: NIS 5,300

On 14 December the owned wallets received two assets only seconds apart:

- 0.06080890 BTC, exactly matching Saar's Bitstamp withdrawal; estimated value
  NIS 3,639.24.
- 0.791 ETH from a noted possible Saar wallet; estimated value NIS 2,071.19.

The combined estimated value is NIS 5,710.43, 7.7% above the combined bank
payments. The timing and combined value make this a plausible bundle. Only the
BTC leg is an exact Bitstamp match; the ETH leg is a Saar-wallet inference.
The evidence does not support assigning one asset to one of the two bank rows.

### Low confidence: 3 December 2017, NIS 2,760 (reference 27791)

The day before this payment, two Bitstamp withdrawals arrived exactly in an
owned wallet: 0.043 ETH and 0.600 ETH. Their estimated combined value was only
NIS 1,037.63, 62.4% below the payment. The timing supports a relationship, but
the value mismatch means this should be treated as a partial delivery or an
unresolved payment rather than a completed one-to-one match.

## Exact exchange-to-wallet evidence

The seven exact matches are:

| Date | Bitstamp amount | Receipt delay | Transaction hash |
|---|---:|---:|---|
| 20 Aug 2017 | 0.12421232 ETH | 13s | `0xfb2182f8a3c0640505dc213a57663d48e525c66b96e841c8abe62120756e76fc` |
| 20 Aug 2017 | 5 ETH | 19s | `0xaf8fc667e7482e1d7e8ba63fb977bae0af9663ce9148bd2b945bd0f6a87c0f3d` |
| 4 Sep 2017 | 3.94414191 ETH | 187s | `0x8d8034dd5292afbc2eb87db3007fd21ef75c4e0802ba45671b83543d3c21a993` |
| 10 Sep 2017 | 6.84111000 ETH | 21s | `0x1397edd5e9afa5a869406cf1d53d91b70048fe042e0a45db9da884f2409a160b` |
| 2 Dec 2017 | 0.04300000 ETH | 64s | `0x7bbaf94acfed626f83cb8218f1eb61e28e44d17b5fb7749e6539dc178df42268` |
| 2 Dec 2017 | 0.60000000 ETH | 67s | `0xe816869b512c6106ce19670391c6f764aec535b6a9395a3d546ac19b88c3ec95` |
| 14 Dec 2017 | 0.06080890 BTC | 447s | `9f68d6ee3e7381ecd7e0bc9bc665dc244c8bee3a31702a53b1b28f5cc7ab3fda` |

## Valuation and limitations

The NIS estimates use the existing project price evidence in
`tax/historical_nis_prices.csv`: nearest Coinbase USD price multiplied by the
Frankfurter USD/ILS reference rate. They are used only as a reasonableness test;
the actual bank payment is the stronger evidence for cost basis when a payment
allocation is accepted.

No Bitstamp USD deposit was labeled as originating from the bank payer, so the
USD-deposit comparisons are candidates, not proof. The exact crypto withdrawal
to blockchain receipt matches are much stronger because amount, coin, and time
all agree independently.
