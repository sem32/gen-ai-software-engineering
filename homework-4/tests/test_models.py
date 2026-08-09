"""Baseline tests for the task model."""

from __future__ import annotations

import pytest

from src.models import PRIORITY_RANK, Task, ValidationError


def test_defaults_are_applied():
    task = Task(id=1, title="  Write docs  ")
    assert task.title == "Write docs"
    assert task.priority == "medium"
    assert task.status == "todo"
    assert task.created_at
    assert task.completed_at is None


def test_done_task_gets_completion_date():
    task = Task(id=1, title="Done thing", status="done")
    assert task.completed_at == task.created_at


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"title": "   "}, "title must not be empty"),
        ({"title": "x", "priority": "later"}, "priority must be one of"),
        ({"title": "x", "status": "archived"}, "status must be one of"),
    ],
)
def test_invalid_input_is_rejected(kwargs, message):
    with pytest.raises(ValidationError) as excinfo:
        Task(id=1, **kwargs)
    assert message in str(excinfo.value)


def test_round_trip_through_dict():
    task = Task(id=7, title="Round trip", priority="urgent", tags=["a", "b"])
    assert Task.from_dict(task.to_dict()) == task


def test_from_dict_rejects_unknown_fields():
    with pytest.raises(ValidationError) as excinfo:
        Task.from_dict({"id": 1, "title": "x", "owner": "nobody"})
    assert "unknown task fields: owner" in str(excinfo.value)


def test_priority_rank_orders_by_severity():
    assert PRIORITY_RANK["urgent"] < PRIORITY_RANK["high"] < PRIORITY_RANK["medium"]
