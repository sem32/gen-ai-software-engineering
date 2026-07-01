#!/usr/bin/env bash
# Exercise every endpoint of the Banking Transactions API.
# Prerequisite: the server is running on http://localhost:3000 (see ./run.sh).
set -euo pipefail

BASE="${BASE_URL:-http://localhost:3000}"
hr() { printf '\n=== %s ===\n' "$1"; }

hr "Create a deposit"
curl -s -X POST "$BASE/transactions" -H "Content-Type: application/json" -d '{
  "toAccount": "ACC-12345", "amount": 1000.00, "currency": "USD",
  "type": "deposit", "timestamp": "2024-01-05T09:00:00Z"
}'

hr "Create a transfer"
curl -s -X POST "$BASE/transactions" -H "Content-Type: application/json" -d '{
  "fromAccount": "ACC-12345", "toAccount": "ACC-67890", "amount": 100.50,
  "currency": "USD", "type": "transfer", "timestamp": "2024-01-10T12:30:00Z"
}'

hr "Create a withdrawal"
curl -s -X POST "$BASE/transactions" -H "Content-Type: application/json" -d '{
  "fromAccount": "ACC-12345", "amount": 250.75, "currency": "USD",
  "type": "withdrawal", "timestamp": "2024-01-20T15:45:00Z"
}'

hr "Validation error (negative amount + bad currency)"
curl -s -X POST "$BASE/transactions" -H "Content-Type: application/json" -d '{
  "fromAccount": "ACC-12345", "toAccount": "ACC-67890",
  "amount": -5, "currency": "XYZ", "type": "transfer"
}'

hr "List all transactions"
curl -s "$BASE/transactions"

hr "Filter by account ACC-12345"
curl -s "$BASE/transactions?accountId=ACC-12345"

hr "Filter by type=transfer and January date range"
curl -s "$BASE/transactions?type=transfer&from=2024-01-01&to=2024-01-31"

hr "Balance for ACC-12345"
curl -s "$BASE/accounts/ACC-12345/balance"

hr "Summary for ACC-12345"
curl -s "$BASE/accounts/ACC-12345/summary"

hr "Simple interest (rate=0.05, days=30) for ACC-12345"
curl -s "$BASE/accounts/ACC-12345/interest?rate=0.05&days=30"

hr "CSV export"
curl -s "$BASE/transactions/export?format=csv"

printf '\n'
