#!/usr/bin/env bash
# Start the Banking Transactions API on port 3000.
# Run from the homework-1/ directory: ./demo/run.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec uvicorn src.main:app --reload --host 0.0.0.0 --port 3000
