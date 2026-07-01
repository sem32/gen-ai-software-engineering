# 🏦 Homework 1: Banking Transactions API

> **Student Name**: Semen Darienko
> **Date Submitted**: 2026-07-01
> **AI Tools Used**: Claude Code (Opus 4.8)

---

## 📋 Project Overview

A minimal REST API for banking transactions built with **Python + FastAPI**, using
**in-memory storage** (no database). It implements all four required task areas plus
**all four** optional Task 4 features.

Monetary amounts are handled with `decimal.Decimal` (never `float`) so that money
arithmetic is exact, and validation follows the assignment's rules for amounts,
account-number format, and ISO 4217 currency codes.

---

## ✅ Features Implemented

### Task 1 — Core API
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/transactions` | Create a transaction (`201`) |
| `GET`  | `/transactions` | List all transactions (with filters) |
| `GET`  | `/transactions/{id}` | Get one transaction (`404` if missing) |
| `GET`  | `/accounts/{accountId}/balance` | Net account balance |

### Task 2 — Validation
- **Amount**: must be positive, at most 2 decimal places.
- **Accounts**: must match `ACC-XXXXX` (alphanumeric after the dash).
- **Currency**: must be a valid ISO 4217 code (case-insensitive input, normalized to upper-case).
- **Type**: `deposit | withdrawal | transfer`, with per-type account requirements.
- Errors return HTTP `400` in the assignment's shape:
  ```json
  {
    "error": "Validation failed",
    "details": [
      {"field": "amount", "message": "Amount must be a positive number"},
      {"field": "currency", "message": "Invalid currency code"}
    ]
  }
  ```

### Task 3 — History filtering (`GET /transactions`)
- `?accountId=ACC-12345` — matches either `fromAccount` or `toAccount`
- `?type=transfer`
- `?from=2024-01-01&to=2024-01-31` — inclusive date range (single day supported)
- Filters are combinable.

### Task 4 — Additional features (all four implemented)
| Option | Endpoint | Notes |
|--------|----------|-------|
| **A. Summary** | `GET /accounts/{id}/summary` | total deposits / withdrawals, transaction count, most recent date |
| **B. Interest** | `GET /accounts/{id}/interest?rate=0.05&days=30` | simple interest on current balance |
| **C. Export** | `GET /transactions/export?format=csv` | CSV export (honours the same filters) |
| **D. Rate limit** | *(middleware)* | 100 req/min per IP → `429 Too Many Requests` |

---

## 🏗️ Architecture

```
src/
├── main.py            # App factory: routers, rate-limit middleware, error handler
├── models.py          # Pydantic models + validation (TransactionCreate, Transaction)
├── constants.py       # ISO 4217 subset, types, statuses, account regex
├── storage.py         # In-memory TransactionStore (process singleton)
├── services.py        # Filtering, balance, summary, interest, CSV serialization
├── rate_limit.py      # Per-IP sliding-window RateLimiter + middleware
└── routers/
    ├── transactions.py  # create / list / get / export
    └── accounts.py      # balance / summary / interest
tests/                  # pytest suite (42 tests, ~96% coverage)
demo/                   # run script + sample requests + sample data
```

**Key design decisions**
- **Decimal money**: amounts are parsed from the raw request via `str()` so literals like
  `100.50` keep exactly two decimal places instead of inheriting float noise.
- **Status semantics**: a transaction defaults to `completed`; only `completed`
  transactions affect balances and monetary totals (`pending`/`failed` are stored and
  counted but do not move money).
- **Balance model**: for each completed transaction, the `toAccount` is credited and the
  `fromAccount` is debited — one rule that works for deposits, withdrawals and transfers.
- **Custom validation errors**: a `RequestValidationError` handler maps Pydantic errors to
  the required `{error, details:[{field, message}]}` body with status `400`.
- **App factory** (`create_app`): the rate limiter reads its limit from env at build time,
  which lets tests spin up an isolated app with a low limit.

---

## 🤖 How AI Was Used

- **Claude Code** scaffolded the FastAPI project structure, models, services, routers, the
  rate-limit middleware, and the pytest suite from `TASKS.md`.
- The initial pinned dependency versions failed to build on Python 3.14 (`pydantic-core`
  needed a Rust toolchain). Claude diagnosed the PyO3/Python-3.14 incompatibility and
  switched `requirements.txt` to minimum-version constraints so prebuilt wheels are used.
- All code was reviewed and every test was executed locally before submission
  (see the coverage report in `docs/screenshots/`).

---

## 🧪 Tests

42 tests covering CRUD, validation and the error shape, history filtering, account
balance/summary/interest, CSV export, and rate limiting. Coverage ≈ **96%**.

```bash
.venv/bin/python -m pytest --cov=src --cov-report=term-missing
```

See **[HOWTORUN.md](./HOWTORUN.md)** for full setup, run, and test instructions.

<div align="center">

*This project was completed as part of the AI-Assisted Development course.*

</div>
