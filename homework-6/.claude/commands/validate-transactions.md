---
description: Validate sample transactions without running the full pipeline (dry run)
argument-hint: [optional path to a transactions JSON file]
allowed-tools: Bash, Read
---

# Validate transactions (dry run)

Validate every transaction in `homework-6/sample-transactions.json` — or in `$ARGUMENTS` if a path
was given — **without** processing them. Nothing may be written under `shared/`.

## Steps

1. **Run the validator in dry-run mode:**
   ```bash
   cd homework-6 && .venv/bin/python agents/transaction_validator.py --dry-run
   ```
   With a custom file: append `--sample <path>`. Fall back to `python3` if the virtualenv is absent.

2. **Report the counts**: total, valid, invalid.

3. **Report the rejection reasons.** The validator emits stable codes — explain each one in plain
   language:

   | Code | Meaning |
   |---|---|
   | `missing_field:<name>` | a required field is absent or blank |
   | `invalid_amount` | the amount is not parseable as an exact decimal (a `float` also fails here) |
   | `non_positive_amount` | the amount is zero or negative — refunds carry a positive amount |
   | `too_many_decimal_places` | more decimals than the currency's minor unit allows |
   | `unknown_currency:<code>` | not an ISO 4217 code in the allow-list |
   | `invalid_timestamp` | not parseable as ISO 8601 |
   | `invalid_account_format:<field>` | the account is not `ACC-` followed by four digits |
   | `same_source_and_destination` | source and destination are the same account |
   | `unknown_transaction_type:<type>` | not in the known transaction-type set |
   | `invalid_metadata` | `metadata` is present but is not an object |

4. **Show the table** the command printed, and confirm that `shared/` was not created or modified.

## Notes

- A record can fail several checks at once — report all of its codes, not just the first.
- This command answers "would the pipeline accept this file?". It does not score risk, screen for
  compliance or settle anything — use `/run-pipeline` for that.
