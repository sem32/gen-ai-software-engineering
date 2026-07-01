# ▶️ How to Run the Application

Banking Transactions API — Python + FastAPI.

## 1. Prerequisites

- **Python 3.10+** (developed and tested on Python 3.14)
- `pip` and `venv` (bundled with Python)

## 2. Setup

From the `homework-1/` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Run the API

```bash
# Option A: helper script
./demo/run.sh

# Option B: directly with uvicorn
uvicorn src.main:app --reload --port 3000
```

The API starts at **http://localhost:3000**.

- Interactive docs (Swagger UI): **http://localhost:3000/docs**
- OpenAPI schema: **http://localhost:3000/openapi.json**

## 4. Try It

Load sample data and exercise every endpoint:

```bash
# with the server running on port 3000
bash demo/sample-requests.sh
```

Or a single request by hand:

```bash
curl -X POST http://localhost:3000/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "fromAccount": "ACC-12345",
    "toAccount": "ACC-67890",
    "amount": 100.50,
    "currency": "USD",
    "type": "transfer"
  }'
```

See **`demo/sample-requests.http`** for a full list you can run from VS Code's REST Client,
and **`demo/sample-data.json`** for ready-made transaction payloads.

## 5. Run the Tests

```bash
# all tests
.venv/bin/python -m pytest

# with coverage report
.venv/bin/python -m pytest --cov=src --cov-report=term-missing

# a single test file
.venv/bin/python -m pytest tests/test_validation.py

# a single test
.venv/bin/python -m pytest tests/test_accounts.py::test_simple_interest_calculation
```

Expected: **42 passed**, coverage ≈ 96%.

## 6. Rate Limiting

The API limits each client IP to **100 requests per minute** and returns `429` when
exceeded. To observe it quickly, lower the limit via environment variables:

```bash
RATE_LIMIT_MAX=5 RATE_LIMIT_WINDOW=60 uvicorn src.main:app --port 3000
# then send 6+ requests; the 6th returns 429
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `RATE_LIMIT_MAX` | `100` | Max requests per window per IP |
| `RATE_LIMIT_WINDOW` | `60` | Window length in seconds |
