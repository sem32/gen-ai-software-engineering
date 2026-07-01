"""Account endpoints and Task 4 features: balance, summary, interest, CSV export."""

from tests.conftest import make_transaction


def _seed_account(client):
    # ACC-11111 receives a deposit of 500 and sends a transfer of 200 → balance 300.
    client.post("/transactions", json=make_transaction(
        fromAccount=None, toAccount="ACC-11111", type="deposit",
        amount=500, timestamp="2024-01-01T09:00:00Z",
    ))
    client.post("/transactions", json=make_transaction(
        fromAccount="ACC-11111", toAccount="ACC-22222", type="transfer",
        amount=200, timestamp="2024-01-02T09:00:00Z",
    ))


def test_balance_reflects_deposits_and_transfers(client):
    _seed_account(client)
    response = client.get("/accounts/ACC-11111/balance")
    assert response.status_code == 200
    assert response.json()["balance"] == 300.0


def test_balance_ignores_non_completed_transactions(client):
    client.post("/transactions", json=make_transaction(
        fromAccount=None, toAccount="ACC-55555", type="deposit",
        amount=1000, status="pending",
    ))
    response = client.get("/accounts/ACC-55555/balance")
    assert response.json()["balance"] == 0.0


def test_unknown_account_has_zero_balance(client):
    response = client.get("/accounts/ACC-00000/balance")
    assert response.status_code == 200
    assert response.json()["balance"] == 0.0


def test_account_summary(client):
    _seed_account(client)
    response = client.get("/accounts/ACC-11111/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["totalDeposits"] == 500.0
    assert body["totalWithdrawals"] == 200.0
    assert body["transactionCount"] == 2
    assert body["mostRecentTransactionDate"].startswith("2024-01-02")


def test_summary_for_account_without_activity(client):
    response = client.get("/accounts/ACC-99999/summary")
    body = response.json()
    assert body["transactionCount"] == 0
    assert body["mostRecentTransactionDate"] is None


def test_simple_interest_calculation(client):
    _seed_account(client)  # balance = 300
    response = client.get("/accounts/ACC-11111/interest", params={"rate": "0.05", "days": 365})
    assert response.status_code == 200
    body = response.json()
    # 300 * 0.05 * 365/365 = 15.00
    assert body["interest"] == 15.0
    assert body["balance"] == 300.0


def test_interest_partial_period(client):
    _seed_account(client)  # balance = 300
    response = client.get("/accounts/ACC-11111/interest", params={"rate": "0.10", "days": 30})
    # 300 * 0.10 * 30/365 = 2.4657... → 2.47
    assert response.json()["interest"] == 2.47


def test_interest_rejects_invalid_rate(client):
    response = client.get("/accounts/ACC-11111/interest", params={"rate": "abc", "days": 30})
    assert response.status_code == 400


def test_csv_export_returns_csv(client):
    _seed_account(client)
    response = client.get("/transactions/export", params={"format": "csv"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0] == "id,fromAccount,toAccount,amount,currency,type,timestamp,status"
    assert len(lines) == 3  # header + 2 rows


def test_csv_export_respects_filters(client):
    _seed_account(client)
    response = client.get("/transactions/export", params={"type": "deposit"})
    lines = response.text.strip().splitlines()
    assert len(lines) == 2  # header + 1 deposit row


def test_export_rejects_unsupported_format(client):
    response = client.get("/transactions/export", params={"format": "pdf"})
    assert response.status_code == 400
