"""Rate limiting (Task 4 Option D)."""

import os

from fastapi.testclient import TestClient

from src.rate_limit import RateLimiter


def test_limiter_allows_up_to_max_then_blocks():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.allow("1.2.3.4", now=0)
    assert limiter.allow("1.2.3.4", now=1)
    assert limiter.allow("1.2.3.4", now=2)
    assert not limiter.allow("1.2.3.4", now=3)  # 4th request blocked


def test_limiter_is_per_key():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("1.1.1.1", now=0)
    assert not limiter.allow("1.1.1.1", now=1)
    assert limiter.allow("2.2.2.2", now=1)  # different IP unaffected


def test_limiter_window_slides():
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    assert limiter.allow("1.1.1.1", now=0)
    assert not limiter.allow("1.1.1.1", now=5)
    assert limiter.allow("1.1.1.1", now=11)  # old hit expired


def test_api_returns_429_when_limit_exceeded(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_MAX", "5")
    monkeypatch.setenv("RATE_LIMIT_WINDOW", "60")
    # Import inside the test so create_app reads the patched environment.
    from src.main import create_app

    app = create_app()
    with TestClient(app) as client:
        statuses = [client.get("/").status_code for _ in range(6)]
    assert statuses[:5] == [200, 200, 200, 200, 200]
    assert statuses[5] == 429
