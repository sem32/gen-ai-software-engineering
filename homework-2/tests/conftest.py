"""Shared pytest fixtures for the Customer Support Ticket API test suite.

Provides a ``TestClient`` fixture, an autouse fixture that resets the shared
in-memory store before every test so tests stay isolated, a ``valid_ticket``
helper that returns a fresh valid create payload, and a ``DEMO`` path pointing
at the repository's ``demo/`` sample-data directory.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.storage import store

# Absolute path to the homework-2/demo directory holding the sample data files.
DEMO = Path(__file__).resolve().parent.parent / "demo"


@pytest.fixture(autouse=True)
def _reset_store():
    """Clear the shared store before each test so tests do not leak state."""
    store.clear()
    yield
    store.clear()


@pytest.fixture
def client():
    """Return a FastAPI TestClient bound to the application."""
    return TestClient(app)


@pytest.fixture
def valid_ticket():
    """Return a factory producing a valid ``TicketCreate`` payload dict.

    Call with keyword overrides to tweak individual fields, e.g.
    ``valid_ticket(priority="high")``.
    """

    def _make(**overrides) -> dict:
        payload = {
            "customer_id": "CUST-0001",
            "customer_email": "customer@example.com",
            "customer_name": "Test Customer",
            "subject": "Test subject line",
            "description": "This is a sufficiently long ticket description for tests.",
            "category": "other",
            "priority": "medium",
            "status": "new",
            "assigned_to": "Agent Smith",
            "tags": ["alpha", "beta"],
            "metadata": {"source": "web_form", "browser": "Chrome", "device_type": "desktop"},
        }
        payload.update(overrides)
        return payload

    return _make
