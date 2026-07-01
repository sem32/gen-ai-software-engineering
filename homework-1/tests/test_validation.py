"""Validation rules and the custom error response shape (Task 2)."""

from tests.conftest import make_transaction


def _fields(response):
    return {d["field"] for d in response.json()["details"]}


def test_negative_amount_is_rejected(client):
    response = client.post("/transactions", json=make_transaction(amount=-5))
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "Validation failed"
    assert "amount" in _fields(response)
    messages = [d["message"] for d in body["details"] if d["field"] == "amount"]
    assert any("positive" in m.lower() for m in messages)


def test_zero_amount_is_rejected(client):
    response = client.post("/transactions", json=make_transaction(amount=0))
    assert response.status_code == 400
    assert "amount" in _fields(response)


def test_amount_with_three_decimals_is_rejected(client):
    response = client.post("/transactions", json=make_transaction(amount="100.123"))
    assert response.status_code == 400
    messages = [d["message"] for d in response.json()["details"] if d["field"] == "amount"]
    assert any("2 decimal" in m for m in messages)


def test_amount_with_two_decimals_is_accepted(client):
    response = client.post("/transactions", json=make_transaction(amount="100.99"))
    assert response.status_code == 201
    assert response.json()["amount"] == 100.99


def test_invalid_currency_is_rejected(client):
    response = client.post("/transactions", json=make_transaction(currency="XYZ"))
    assert response.status_code == 400
    assert "currency" in _fields(response)


def test_currency_is_normalized_to_uppercase(client):
    response = client.post("/transactions", json=make_transaction(currency="eur"))
    assert response.status_code == 201
    assert response.json()["currency"] == "EUR"


def test_invalid_account_format_is_rejected(client):
    response = client.post("/transactions", json=make_transaction(fromAccount="12345"))
    assert response.status_code == 400
    assert "fromAccount" in _fields(response)


def test_valid_account_formats_are_accepted(client):
    response = client.post(
        "/transactions",
        json=make_transaction(fromAccount="ACC-ABC12", toAccount="ACC-99999"),
    )
    assert response.status_code == 201


def test_invalid_type_is_rejected(client):
    response = client.post("/transactions", json=make_transaction(type="payment"))
    assert response.status_code == 400
    assert "type" in _fields(response)


def test_transfer_requires_both_accounts(client):
    payload = make_transaction(type="transfer", toAccount=None)
    response = client.post("/transactions", json=payload)
    assert response.status_code == 400


def test_multiple_validation_errors_are_all_reported(client):
    payload = make_transaction(amount=-1, currency="XYZ")
    response = client.post("/transactions", json=payload)
    assert response.status_code == 400
    fields = _fields(response)
    assert "amount" in fields
    assert "currency" in fields


def test_missing_amount_is_rejected(client):
    payload = make_transaction()
    del payload["amount"]
    response = client.post("/transactions", json=payload)
    assert response.status_code == 400
