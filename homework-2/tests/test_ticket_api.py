"""API endpoint tests for the ticket CRUD + filtering surface."""


def _create(client, valid_ticket, **overrides):
    resp = client.post("/tickets", json=valid_ticket(**overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_ticket_returns_201_with_server_fields(client, valid_ticket):
    resp = client.post("/tickets", json=valid_ticket())
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"]
    assert body["subject"] == "Test subject line"
    assert body["created_at"] is not None
    assert body["resolved_at"] is None


def test_create_ticket_with_auto_classify_flag(client, valid_ticket):
    resp = client.post(
        "/tickets?auto_classify=true",
        json=valid_ticket(subject="Cannot login", description="I forgot my password and cannot login at all"),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["category"] == "account_access"
    assert body["classification"] is not None


def test_list_tickets_returns_all(client, valid_ticket):
    _create(client, valid_ticket, customer_id="CUST-A")
    _create(client, valid_ticket, customer_id="CUST-B")
    resp = client.get("/tickets")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_ticket_returns_200(client, valid_ticket):
    created = _create(client, valid_ticket)
    resp = client.get(f"/tickets/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_missing_ticket_returns_404(client):
    resp = client.get("/tickets/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Ticket not found"


def test_update_ticket_partial(client, valid_ticket):
    created = _create(client, valid_ticket)
    resp = client.put(f"/tickets/{created['id']}", json={"subject": "Updated subject"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["subject"] == "Updated subject"
    # Untouched fields are preserved.
    assert body["customer_id"] == created["customer_id"]


def test_update_status_resolved_sets_resolved_at(client, valid_ticket):
    created = _create(client, valid_ticket)
    assert created["resolved_at"] is None
    resp = client.put(f"/tickets/{created['id']}", json={"status": "resolved"})
    assert resp.status_code == 200
    assert resp.json()["resolved_at"] is not None


def test_update_missing_ticket_returns_404(client):
    resp = client.put("/tickets/nope", json={"subject": "x subject"})
    assert resp.status_code == 404


def test_delete_ticket_returns_204(client, valid_ticket):
    created = _create(client, valid_ticket)
    resp = client.delete(f"/tickets/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/tickets/{created['id']}").status_code == 404


def test_delete_missing_ticket_returns_404(client):
    resp = client.delete("/tickets/ghost")
    assert resp.status_code == 404


def test_filter_by_category(client, valid_ticket):
    _create(client, valid_ticket, category="billing_question")
    _create(client, valid_ticket, category="technical_issue")
    resp = client.get("/tickets", params={"category": "billing_question"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["category"] == "billing_question"


def test_filter_by_priority(client, valid_ticket):
    _create(client, valid_ticket, priority="urgent")
    _create(client, valid_ticket, priority="low")
    resp = client.get("/tickets", params={"priority": "urgent"})
    assert len(resp.json()) == 1


def test_filter_by_status(client, valid_ticket):
    _create(client, valid_ticket, status="new")
    _create(client, valid_ticket, status="in_progress")
    resp = client.get("/tickets", params={"status": "in_progress"})
    assert len(resp.json()) == 1


def test_filter_by_assigned_to(client, valid_ticket):
    _create(client, valid_ticket, assigned_to="Alice")
    _create(client, valid_ticket, assigned_to="Bob")
    resp = client.get("/tickets", params={"assigned_to": "Alice"})
    assert len(resp.json()) == 1


def test_filter_by_customer_id(client, valid_ticket):
    _create(client, valid_ticket, customer_id="CUST-X")
    _create(client, valid_ticket, customer_id="CUST-Y")
    resp = client.get("/tickets", params={"customer_id": "CUST-Y"})
    assert len(resp.json()) == 1


def test_filter_by_tag(client, valid_ticket):
    _create(client, valid_ticket, tags=["urgent-tag", "vip"])
    _create(client, valid_ticket, tags=["other"])
    resp = client.get("/tickets", params={"tag": "vip"})
    assert len(resp.json()) == 1


def test_root_health_endpoint(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_update_with_invalid_value_returns_400(client, valid_ticket):
    created = _create(client, valid_ticket)
    resp = client.put(f"/tickets/{created['id']}", json={"priority": "nope"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "Validation failed"


def test_update_empty_subject_returns_400(client, valid_ticket):
    created = _create(client, valid_ticket)
    resp = client.put(f"/tickets/{created['id']}", json={"subject": ""})
    assert resp.status_code == 400


def test_filter_combined_category_and_priority(client, valid_ticket):
    _create(client, valid_ticket, category="billing_question", priority="urgent")
    _create(client, valid_ticket, category="billing_question", priority="low")
    _create(client, valid_ticket, category="technical_issue", priority="urgent")
    resp = client.get("/tickets", params={"category": "billing_question", "priority": "urgent"})
    results = resp.json()
    assert len(results) == 1
    assert results[0]["category"] == "billing_question"
    assert results[0]["priority"] == "urgent"
