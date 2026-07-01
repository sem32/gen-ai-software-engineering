"""Shared pytest fixtures.

The rate limit is set very high here (before the app is imported) so that the
functional test suite is never throttled; dedicated rate-limit tests build their
own app instance with a low limit.
"""

import os

os.environ.setdefault("RATE_LIMIT_MAX", "1000000")
os.environ.setdefault("RATE_LIMIT_WINDOW", "60")

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.storage import store


@pytest.fixture(autouse=True)
def _reset_state():
    """Ensure every test starts with an empty store and fresh limiter."""
    store.clear()
    app.state.rate_limiter.reset()
    yield
    store.clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def make_transaction(**overrides):
    """Return a valid transaction payload with optional field overrides."""
    payload = {
        "fromAccount": "ACC-12345",
        "toAccount": "ACC-67890",
        "amount": 100.50,
        "currency": "USD",
        "type": "transfer",
    }
    payload.update(overrides)
    return payload
