"""Token check guarding the destructive ``admin`` sub-commands."""

from __future__ import annotations

import hmac
import os

ENV_VAR = "TASKTRACKER_ADMIN_TOKEN"


class AuthError(Exception):
    """Raised when an admin action is attempted without a valid token."""


def expected_token() -> str:
    """Return the admin token this installation expects.

    Raises :class:`AuthError` when no token is configured: there is no built-in
    default, so admin commands stay unavailable until an operator sets the
    environment variable.
    """
    configured = os.environ.get(ENV_VAR, "")
    if not configured:
        raise AuthError(f"admin commands are disabled: {ENV_VAR} is not configured")
    return configured


def verify_admin_token(provided: str | None) -> bool:
    """Return True when ``provided`` matches the configured admin token.

    The comparison is constant-time. Raises :class:`AuthError` when no admin
    token is configured for this installation.
    """
    expected = expected_token()
    if provided is None:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_admin(provided: str | None) -> None:
    """Raise :class:`AuthError` unless ``provided`` is the admin token."""
    if not verify_admin_token(provided):
        raise AuthError("admin token rejected")
