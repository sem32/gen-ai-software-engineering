"""Regression tests for BUG-001 fix in ``src/stats.py`` (average_completion_days).

Defect S1: ``average_completion_days`` raised ``ZeroDivisionError`` when the task
collection had no completed tasks (division by ``len(completed) == 0``). The fix
adds an early return of ``0.0``, matching how ``completion_rate`` represents "no
data".
"""

from __future__ import annotations

from src.models import Task
from src.stats import average_completion_days


def test_average_completion_days_with_no_completed_tasks_returns_zero():
    """S1 regression: pre-fix this raised ZeroDivisionError (0/0)."""
    tasks = [
        Task(id=1, title="Not done", status="todo", created_at="2026-01-01"),
        Task(id=2, title="Still going", status="in_progress", created_at="2026-01-02"),
    ]
    assert average_completion_days(tasks) == 0.0


def test_average_completion_days_of_empty_collection_is_zero():
    """S1 boundary: the empty-collection edge the ZeroDivisionError lived on."""
    assert average_completion_days([]) == 0.0


def test_average_completion_days_averages_across_multiple_completed_tasks():
    """S1 neighbour: mean computation over more than one completed task is unaffected
    by the new empty-collection guard."""
    tasks = [
        Task(
            id=1,
            title="Quick one",
            status="done",
            created_at="2026-01-01",
            completed_at="2026-01-03",
        ),
        Task(
            id=2,
            title="Slow one",
            status="done",
            created_at="2026-02-01",
            completed_at="2026-02-07",
        ),
    ]
    assert average_completion_days(tasks) == 4.0
