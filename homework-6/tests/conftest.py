"""Shared fixtures. Every test gets its own workspace — never the repository's real ``shared/``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The project root must sit *after* site-packages on sys.path: `homework-6/mcp/` would otherwise
# shadow the installed `mcp` package that FastMCP imports. Normalise however pytest was launched.
sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != ROOT]
sys.path.append(str(ROOT))

import pytest  # noqa: E402

from agents.protocol import Workspace, build_message  # noqa: E402

SAMPLE_PATH = ROOT / "sample-transactions.json"


@pytest.fixture
def workspace(tmp_path) -> Workspace:
    """An isolated shared workspace under ``tmp_path``."""
    return Workspace.create(tmp_path / "shared", reset=True)


@pytest.fixture(scope="session")
def sample_transactions() -> list[dict]:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def make_transaction():
    """Factory producing a valid raw transaction, overridable field by field."""

    def _make(**overrides):
        transaction = {
            "transaction_id": "TXN900",
            "timestamp": "2026-03-16T09:00:00Z",
            "source_account": "ACC-1001",
            "destination_account": "ACC-2001",
            "amount": "1500.00",
            "currency": "USD",
            "transaction_type": "transfer",
            "description": "Monthly rent payment",
            "metadata": {"channel": "online", "country": "US"},
        }
        transaction.update(overrides)
        return transaction

    return _make


@pytest.fixture
def completed_run(tmp_path):
    """A full pipeline run against the real sample file, inside an isolated workspace."""
    from types import SimpleNamespace

    from integrator import run_pipeline

    shared = tmp_path / "shared"
    summary = run_pipeline(SAMPLE_PATH, shared, verbose=False)
    return SimpleNamespace(shared=shared, workspace=Workspace(root=shared), summary=summary)


@pytest.fixture
def make_message(make_transaction):
    """Factory producing a protocol message wrapping a transaction payload."""

    def _make(target_agent="transaction_validator", source_agent="integrator", **overrides):
        return build_message(
            source_agent=source_agent,
            target_agent=target_agent,
            message_type="transaction",
            data=make_transaction(**overrides),
        )

    return _make
