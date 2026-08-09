# Pipeline run summary

- Generated at: `2026-08-09T22:54:29Z`
- Transactions processed: **8**

## Outcomes

| Status | Count |
|---|---|
| held | 1 |
| rejected | 2 |
| settled | 5 |

## Risk levels

| Level | Count |
|---|---|
| high | 1 |
| low | 2 |
| medium | 3 |

## Volume by currency

| Currency | Bucket | Amount |
|---|---|---|
| EUR | settled_fees | 1.25 |
| EUR | settled_gross | 500.00 |
| EUR | settled_net | 498.75 |
| USD | held | 75000.00 |
| USD | settled_fees | 61.75 |
| USD | settled_gross | 39699.99 |
| USD | settled_net | 39638.24 |

## Transactions

| Transaction | Status | Amount | Risk | Detail |
|---|---|---|---|---|
| TXN001 | settled | 1500.00 USD | 0 (low) | net 1496.25 value date 2026-03-17 |
| TXN002 | settled | 25000.00 USD | 40 (medium) | net 24975.00 value date 2026-03-18 |
| TXN003 | settled | 9999.99 USD | 35 (medium) | net 9974.99 value date 2026-03-17 |
| TXN004 | settled | 500.00 EUR | 40 (medium) | net 498.75 value date 2026-03-17 |
| TXN005 | held | 75000.00 USD | 60 (high) | fraud_review_required |
| TXN006 | rejected | 200.00 XYZ | - | unknown_currency:XYZ |
| TXN007 | rejected | -100.00 GBP | - | non_positive_amount |
| TXN008 | settled | 3200.00 USD | 0 (low) | net 3192.00 value date 2026-03-17 |

## Rejected transactions

- **TXN006** — unknown_currency:XYZ
- **TXN007** — non_positive_amount

## Held transactions

- **TXN005** — fraud_review_required
