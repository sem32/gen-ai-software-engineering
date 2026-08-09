"""Aggregate statistics over a task collection."""

from __future__ import annotations

from datetime import date

from .models import PRIORITIES, STATUSES, Task


def _parse(value: str) -> date:
    return date.fromisoformat(value)


def completion_days(task: Task) -> int:
    """Whole days between creation and completion of a finished task."""
    if task.status != "done" or not task.completed_at:
        raise ValueError(f"task {task.id} is not completed")
    return (_parse(task.completed_at) - _parse(task.created_at)).days


def count_by_status(tasks: list[Task]) -> dict[str, int]:
    """Number of tasks per status, including statuses with no tasks."""
    counts = {status: 0 for status in STATUSES}
    for task in tasks:
        counts[task.status] += 1
    return counts


def count_by_priority(tasks: list[Task]) -> dict[str, int]:
    """Number of tasks per priority, including priorities with no tasks."""
    counts = {priority: 0 for priority in PRIORITIES}
    for task in tasks:
        counts[task.priority] += 1
    return counts


def completion_rate(tasks: list[Task]) -> float:
    """Share of tasks that are done, as a percentage rounded to 1 decimal."""
    if not tasks:
        return 0.0
    done = sum(1 for task in tasks if task.status == "done")
    return round(done * 100 / len(tasks), 1)


def average_completion_days(tasks: list[Task]) -> float:
    """Mean number of days it took to finish the completed tasks.

    A collection with no completed tasks has no average; it reports ``0.0``,
    matching how :func:`completion_rate` represents "no data".
    """
    completed = [task for task in tasks if task.status == "done" and task.completed_at]
    if not completed:
        return 0.0
    total_days = sum(completion_days(task) for task in completed)
    return round(total_days / len(completed), 2)


def summarize(tasks: list[Task]) -> dict:
    """Full statistics payload used by the ``stats`` command."""
    return {
        "total": len(tasks),
        "by_status": count_by_status(tasks),
        "by_priority": count_by_priority(tasks),
        "completion_rate_pct": completion_rate(tasks),
        "average_completion_days": average_completion_days(tasks),
    }
