"""Transaction history filtering on GET /transactions (Task 3)."""

from tests.conftest import make_transaction


def _seed(client):
    client.post("/transactions", json=make_transaction(
        fromAccount="ACC-11111", toAccount="ACC-22222", type="transfer",
        amount=100, timestamp="2024-01-05T10:00:00Z",
    ))
    client.post("/transactions", json=make_transaction(
        fromAccount=None, toAccount="ACC-11111", type="deposit",
        amount=200, timestamp="2024-01-15T10:00:00Z",
    ))
    client.post("/transactions", json=make_transaction(
        fromAccount="ACC-33333", toAccount="ACC-44444", type="transfer",
        amount=300, timestamp="2024-02-10T10:00:00Z",
    ))


def test_filter_by_account_matches_from_or_to(client):
    _seed(client)
    response = client.get("/transactions", params={"accountId": "ACC-11111"})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_filter_by_type(client):
    _seed(client)
    response = client.get("/transactions", params={"type": "deposit"})
    assert len(response.json()) == 1
    assert response.json()[0]["type"] == "deposit"


def test_filter_by_date_range_inclusive(client):
    _seed(client)
    response = client.get("/transactions", params={"from": "2024-01-01", "to": "2024-01-31"})
    assert len(response.json()) == 2


def test_filter_by_single_day(client):
    _seed(client)
    response = client.get("/transactions", params={"from": "2024-01-05", "to": "2024-01-05"})
    assert len(response.json()) == 1


def test_combined_filters(client):
    _seed(client)
    response = client.get(
        "/transactions",
        params={"accountId": "ACC-11111", "type": "transfer", "from": "2024-01-01", "to": "2024-01-31"},
    )
    assert len(response.json()) == 1
    assert response.json()[0]["fromAccount"] == "ACC-11111"


def test_invalid_date_filter_returns_400(client):
    _seed(client)
    response = client.get("/transactions", params={"from": "not-a-date"})
    assert response.status_code == 400
