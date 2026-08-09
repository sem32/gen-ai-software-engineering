"""Regression tests for BUG-001 fixes in ``src/auth.py``.

Defect S3a: ``expected_token`` fell back to the hardcoded
``DEFAULT_ADMIN_TOKEN = "hw4-admin-secret"`` whenever ``TASKTRACKER_ADMIN_TOKEN``
was unset, letting anyone run ``admin clear`` against any unconfigured install.
The fix removes the default and raises :class:`AuthError` instead.

Defect S3b: ``verify_admin_token`` used ``==`` (not constant-time) and
``require_admin`` echoed the caller-supplied token in its error message. The fix
uses ``hmac.compare_digest`` and a plain, non-interpolated rejection message.
"""

from __future__ import annotations

import pytest

from src.auth import ENV_VAR, AuthError, expected_token, require_admin, verify_admin_token


def test_expected_token_raises_when_env_var_unset(monkeypatch):
    """S3a regression: pre-fix this silently returned the hardcoded default token."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(
        AuthError, match=f"admin commands are disabled: {ENV_VAR} is not configured"
    ):
        expected_token()


def test_expected_token_raises_when_env_var_is_empty_string(monkeypatch):
    """S3a boundary: an empty-string value is treated the same as unset, not as a
    valid (empty) token."""
    monkeypatch.setenv(ENV_VAR, "")
    with pytest.raises(AuthError):
        expected_token()


def test_expected_token_returns_configured_value(monkeypatch):
    """S3a neighbour: a properly configured token is still returned unchanged."""
    monkeypatch.setenv(ENV_VAR, "s3cret")
    assert expected_token() == "s3cret"


def test_require_admin_rejection_message_does_not_echo_supplied_token(monkeypatch):
    """S3b regression: pre-fix the error message interpolated the caller-supplied
    token via ``{provided!r}``."""
    monkeypatch.setenv(ENV_VAR, "correct-token")
    with pytest.raises(AuthError) as excinfo:
        require_admin("attacker-supplied-secret")
    assert str(excinfo.value) == "admin token rejected"
    assert "attacker-supplied-secret" not in str(excinfo.value)


def test_verify_admin_token_with_none_raises_when_no_token_configured(monkeypatch):
    """S3b boundary: pre-fix, ``provided is None`` short-circuited to False before
    ``expected_token()`` was ever called, silently masking a missing configuration.
    Post-fix, ``expected_token()`` runs unconditionally first, so an unconfigured
    install now raises AuthError even for a ``None`` input."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(AuthError):
        verify_admin_token(None)


def test_verify_admin_token_returns_false_for_none_when_token_is_configured(monkeypatch):
    """S3b neighbour: with a token configured, explicit ``None`` input still
    short-circuits to False, unchanged by the reordering above."""
    monkeypatch.setenv(ENV_VAR, "correct-token")
    assert verify_admin_token(None) is False


def test_verify_admin_token_returns_true_for_matching_token(monkeypatch):
    """S3b neighbour: the constant-time comparison still accepts the correct
    token."""
    monkeypatch.setenv(ENV_VAR, "correct-token")
    assert verify_admin_token("correct-token") is True


def test_verify_admin_token_returns_false_for_wrong_token(monkeypatch):
    """S3b neighbour: a non-matching token is still rejected under
    ``hmac.compare_digest``."""
    monkeypatch.setenv(ENV_VAR, "correct-token")
    assert verify_admin_token("wrong-token") is False
