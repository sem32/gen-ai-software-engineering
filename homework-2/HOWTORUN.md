# Customer Support Ticket API — How to Run

> **Author**: Simon Darienko

## 1. Prerequisites

- **Python 3.10+** (developed on 3.14)
- **pip** (Python package manager)
- **venv** (built-in virtual environment module)

## 2. Setup

From the `homework-2/` directory, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, use:
```bash
.venv\Scripts\activate
```

Then install dependencies:
```bash
pip install -r requirements.txt
```

## 3. Run the API

Start the API server:

```bash
uvicorn src.main:app --reload --port 8000
```

Once running:
- **API base URL**: http://localhost:8000
- **Swagger interactive docs**: http://localhost:8000/docs
- **OpenAPI schema**: http://localhost:8000/openapi.json

## 4. Try It (cURL Examples)

### Create a ticket

```bash
curl -X POST http://localhost:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id":"CUST-1001",
    "customer_email":"jane@example.com",
    "customer_name":"Jane Doe",
    "subject":"Cannot log in",
    "description":"I reset my password but still cannot access my account."
  }'
```

### Create with auto-classification

Add `?auto_classify=true` to the URL:
```bash
curl -X POST http://localhost:8000/tickets?auto_classify=true \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"CUST-1002","customer_email":"john@example.com","customer_name":"John Smith","subject":"Billing error","description":"I was charged twice for my subscription."}'
```

### List tickets with filter

```bash
curl "http://localhost:8000/tickets?priority=urgent"
```

### Import tickets from a file

For CSV:
```bash
curl -X POST "http://localhost:8000/tickets/import?format=csv" \
  -F "file=@demo/sample_tickets.csv"
```

For JSON:
```bash
curl -X POST "http://localhost:8000/tickets/import?format=json" \
  -F "file=@demo/sample_tickets.json"
```

For XML:
```bash
curl -X POST "http://localhost:8000/tickets/import?format=xml" \
  -F "file=@demo/sample_tickets.xml"
```

### Auto-classify an existing ticket

```bash
curl -X POST http://localhost:8000/tickets/{id}/auto-classify
```

Replace `{id}` with the actual ticket ID.

## 5. Run the Tests

Run all tests:

```bash
.venv/bin/python -m pytest
```

Run with coverage report:

```bash
.venv/bin/python -m pytest --cov=src --cov-report=term-missing
```

**Expected results**: 78 passed, ~95% coverage

Run tests from a single file:

```bash
.venv/bin/python -m pytest tests/test_import_csv.py
```

## 6. Sample Data

The `demo/` directory contains test data files:

- **sample_tickets.csv** — 50 rows of sample tickets
- **sample_tickets.json** — 20 sample tickets in JSON format
- **sample_tickets.xml** — 30 sample tickets in XML format
- **Invalid/malformed files** — for negative testing

Use these files with the `/tickets/import` endpoint to test bulk import functionality.

## 7. Troubleshooting

- **Import endpoint not working**: Ensure `python-multipart` is installed (already included in `requirements.txt`). Reinstall if needed: `pip install python-multipart`
- **`uvicorn` not found**: Verify the virtual environment is activated. Run `source .venv/bin/activate` (or `.venv\Scripts\activate` on Windows) and try again.
- **Port 8000 already in use**: Pass `--port` with a different port number, e.g., `uvicorn src.main:app --reload --port 8001`
