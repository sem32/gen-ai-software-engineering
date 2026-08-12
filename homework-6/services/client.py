"""Stdlib HTTP client for service-to-service calls (CR-02.2, spec task T-18).

Five nested synchronous hops make the failure modes real, so this is not a one-line ``urlopen``:

* a **per-hop timeout**, because a hung successor must not hang the whole chain;
* **bounded retries with backoff**, but only for faults that can plausibly succeed on a retry;
* a hard distinction between a **downstream business verdict** (4xx — propagate as-is, retrying would
  be wrong) and a **transport fault** (5xx, connection refused, timeout — retryable).

``urllib.request`` keeps the zero-dependency property of the project.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = 0.15
JSON_CONTENT_TYPE = "application/json; charset=utf-8"


class TransportError(RuntimeError):
    """A hop could not be completed: connection refused, timeout, or a 5xx after every retry."""

    def __init__(self, url: str, detail: str, attempts: int) -> None:
        super().__init__(f"{url} failed after {attempts} attempt(s): {detail}")
        self.url = url
        self.detail = detail
        self.attempts = attempts


@dataclass(frozen=True)
class HttpResult:
    """One completed HTTP exchange, however it ended."""

    status: int
    payload: Any
    request_id: str | None = None

    @property
    def is_success(self) -> bool:
        return 200 <= self.status < 300

    @property
    def is_client_error(self) -> bool:
        """A downstream *verdict* — retrying an identical request would produce the same answer."""
        return 400 <= self.status < 500


def post_json(
    url: str,
    payload: Any,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF_SECONDS,
    headers: dict[str, str] | None = None,
) -> HttpResult:
    """POST JSON and return the result. Raises :class:`TransportError` only for transport faults."""
    body = json.dumps(payload).encode("utf-8")
    attempts = 0
    last_detail = "unknown"

    for attempt in range(retries + 1):
        attempts = attempt + 1
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("Content-Type", JSON_CONTENT_TYPE)
        for name, value in (headers or {}).items():
            request.add_header(name, value)

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return _result_from(response.status, response.read(), response.headers)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            result = _result_from(exc.code, raw, exc.headers)
            if result.is_client_error:
                # A business verdict from downstream. Propagate it; do not retry.
                return result
            last_detail = f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            last_detail = f"{type(exc.reason).__name__ if exc.reason else 'URLError'}: {exc.reason}"
        except TimeoutError:
            last_detail = f"timed out after {timeout}s"

        if attempt < retries:
            time.sleep(backoff * (2**attempt))

    raise TransportError(url, last_detail, attempts)


def get_json(url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> HttpResult:
    """GET JSON once — used for health checks, where a retry loop belongs to the caller."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return _result_from(response.status, response.read(), response.headers)
    except urllib.error.HTTPError as exc:
        return _result_from(exc.code, exc.read(), exc.headers)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise TransportError(url, str(getattr(exc, "reason", exc)), 1) from exc


def wait_until_healthy(url: str, *, timeout: float = 15.0, interval: float = 0.1) -> bool:
    """Poll a health endpoint until it answers. Polling, never a blind sleep (spec §3.10)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if get_json(url, timeout=1.0).is_success:
                return True
        except TransportError:
            pass
        time.sleep(interval)
    return False


def _result_from(status: int, raw: bytes, headers: Any) -> HttpResult:
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {"raw": raw[:512].decode("utf-8", errors="replace")}
    request_id = None
    if headers is not None:
        request_id = headers.get("X-Request-Id")
    return HttpResult(status=status, payload=payload, request_id=request_id)
