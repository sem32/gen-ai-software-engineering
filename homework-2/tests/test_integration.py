"""End-to-end integration tests (Task 5)."""

from concurrent.futures import ThreadPoolExecutor

from conftest import DEMO


def test_full_ticket_lifecycle(client, valid_ticket):
    # Create
    created = client.post("/tickets", json=valid_ticket(status="new")).json()
    tid = created["id"]

    # Update (in progress + assignment)
    updated = client.put(
        f"/tickets/{tid}", json={"status": "in_progress", "assigned_to": "Agent K"}
    ).json()
    assert updated["status"] == "in_progress"
    assert updated["assigned_to"] == "Agent K"
    assert updated["resolved_at"] is None

    # Resolve
    resolved = client.put(f"/tickets/{tid}", json={"status": "resolved"}).json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None

    # Get reflects final state
    fetched = client.get(f"/tickets/{tid}").json()
    assert fetched["status"] == "resolved"
    assert fetched["resolved_at"] == resolved["resolved_at"]


def test_bulk_import_with_auto_classification(client):
    with open(DEMO / "sample_tickets.csv", "rb") as fh:
        resp = client.post(
            "/tickets/import?format=csv&auto_classify=true",
            files={"file": ("sample_tickets.csv", fh, "text/csv")},
        )
    assert resp.status_code == 200
    assert resp.json()["successful"] == 50

    tickets = client.get("/tickets").json()
    assert len(tickets) == 50
    # Every imported ticket carries a classification result.
    assert all(t["classification"] is not None for t in tickets)
    assert all(0.0 <= t["classification"]["confidence"] <= 1.0 for t in tickets)


def test_concurrent_create_operations(client, valid_ticket):
    def _create(i):
        return client.post("/tickets", json=valid_ticket(customer_id=f"CUST-{i}")).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(_create, range(25)))

    assert statuses == [201] * 25
    assert len(client.get("/tickets").json()) == 25


def test_combined_filtering_category_and_priority(client, valid_ticket):
    client.post("/tickets", json=valid_ticket(category="billing_question", priority="urgent"))
    client.post("/tickets", json=valid_ticket(category="billing_question", priority="low"))
    client.post("/tickets", json=valid_ticket(category="technical_issue", priority="urgent"))

    resp = client.get("/tickets", params={"category": "billing_question", "priority": "urgent"})
    results = resp.json()
    assert len(results) == 1
    assert results[0]["category"] == "billing_question"
    assert results[0]["priority"] == "urgent"


def test_import_then_filter_end_to_end(client):
    with open(DEMO / "sample_tickets.json", "rb") as fh:
        client.post(
            "/tickets/import?format=json",
            files={"file": ("sample_tickets.json", fh, "application/json")},
        )
    # Filter the imported data by a known category from the sample file.
    resp = client.get("/tickets", params={"category": "feature_request"})
    results = resp.json()
    assert results
    assert all(t["category"] == "feature_request" for t in results)
