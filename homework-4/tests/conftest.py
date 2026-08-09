"""Shared fixtures for the Task Tracker test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import Task  # noqa: E402
from src.storage import TaskStore  # noqa: E402


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """Path to an isolated JSON store inside a per-test temporary directory."""
    return tmp_path / "tasks.json"


@pytest.fixture
def store(store_path: Path) -> TaskStore:
    """An empty :class:`TaskStore` backed by a temporary file."""
    return TaskStore(store_path)


@pytest.fixture
def sample_tasks() -> list[Task]:
    """Three tasks: one done, one in progress, one to do."""
    return [
        Task(
            id=1,
            title="Ship the release",
            priority="high",
            status="done",
            created_at="2026-01-01",
            completed_at="2026-01-05",
        ),
        Task(id=2, title="Answer support ticket", priority="urgent", created_at="2026-01-02"),
        Task(
            id=3,
            title="Update the changelog",
            priority="low",
            status="in_progress",
            created_at="2026-01-03",
        ),
    ]
