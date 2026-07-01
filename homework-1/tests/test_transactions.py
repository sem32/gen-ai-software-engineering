"""Core CRUD behaviour for the /transactions endpoints."""

from tests.conftest import make_transaction


def test_create_transaction_returns_201_and_generated_fields(client):
    response = client.post("/transactions", json=make_transaction())
    assert response.status_code == 201
    body = response.json()
    assert body["id"]  # auto-generated, non-empty
    assert body["fromAccount"] == "ACC-12345"
    assert body["toAccount"] == "ACC-67890"
    assert body["amount"] == 100.50
    assert body["currency"] == "USD"
    assert body["type"] == "transfer"
    assert body["status"] == "completed"
    assert body["timestamp"]  # auto-generated ISO timestamp


def test_created_transaction_has_unique_ids(client):
    first = client.post("/transactions", json=make_transaction()).json()
    second = client.post("/transactions", json=make_transaction()).json()
    assert first["id"] != second["id"]


def test_list_transactions_returns_all(client):
    client.post("/transactions", json=make_transaction())
    client.post("/transactions", json=make_transaction(type="deposit", fromAccount=None))
    response = client.get("/transactions")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_transactions_empty_by_default(client):
    response = client.get("/transactions")
    assert response.status_code == 200
    assert response.json() == []


def test_get_transaction_by_id(client):
    created = client.post("/transactions", json=make_transaction()).json()
    response = client.get(f"/transactions/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unknown_transaction_returns_404(client):
    response = client.get("/transactions/does-not-exist")
    assert response.status_code == 404


def test_deposit_without_from_account_is_allowed(client):
    payload = make_transaction(type="deposit", fromAccount=None, toAccount="ACC-11111")
    response = client.post("/transactions", json=payload)
    assert response.status_code == 201
    assert response.json()["fromAccount"] is None


def test_withdrawal_without_to_account_is_allowed(client):
    payload = make_transaction(type="withdrawal", toAccount=None, fromAccount="ACC-11111")
    response = client.post("/transactions", json=payload)
    assert response.status_code == 201
    assert response.json()["toAccount"] is None


def test_client_supplied_status_is_respected(client):
    response = client.post("/transactions", json=make_transaction(status="pending"))
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
