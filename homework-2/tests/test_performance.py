"""Lightweight performance benchmarks with generous, non-flaky thresholds."""

import time

from conftest import DEMO
from src.classification import classify


def test_bulk_import_50_rows_under_threshold(client):
    with open(DEMO / "sample_tickets.csv", "rb") as fh:
        start = time.perf_counter()
        resp = client.post(
            "/tickets/import?format=csv",
            files={"file": ("sample_tickets.csv", fh, "text/csv")},
        )
        elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert resp.json()["successful"] == 50
    assert elapsed < 5.0, f"bulk import took {elapsed:.3f}s"


def test_single_create_latency(client, valid_ticket):
    start = time.perf_counter()
    resp = client.post("/tickets", json=valid_ticket())
    elapsed = time.perf_counter() - start
    assert resp.status_code == 201
    assert elapsed < 1.0, f"single create took {elapsed:.3f}s"


def test_list_with_many_tickets(client, valid_ticket):
    for i in range(200):
        client.post("/tickets", json=valid_ticket(customer_id=f"CUST-{i}"))
    start = time.perf_counter()
    resp = client.get("/tickets")
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert len(resp.json()) == 200
    assert elapsed < 2.0, f"list took {elapsed:.3f}s"


def test_classify_throughput():
    start = time.perf_counter()
    for _ in range(1000):
        classify("Cannot login", "password reset authentication error crash slow")
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"1000 classify calls took {elapsed:.3f}s"


def test_filter_over_many_tickets(client, valid_ticket):
    for i in range(200):
        category = "billing_question" if i % 2 == 0 else "technical_issue"
        client.post("/tickets", json=valid_ticket(customer_id=f"CUST-{i}", category=category))
    start = time.perf_counter()
    resp = client.get("/tickets", params={"category": "billing_question"})
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert len(resp.json()) == 100
    assert elapsed < 2.0, f"filter took {elapsed:.3f}s"
