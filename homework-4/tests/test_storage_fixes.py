"""Regression tests for BUG-001 fixes in ``src/storage.py``.

Defect S2: ``list_tasks(sort="priority")`` sorted alphabetically instead of by
severity, and had no deterministic tie-break. The fix sorts by
``(PRIORITY_RANK[task.priority], task.created_at, task.id)``.

Defect S3.2 / F4: ``export_report`` allowed ``..`` traversal and absolute
filenames to escape ``export_dir``. The fix rejects any filename that does not
resolve to a location inside ``export_dir`` before writing anything.
"""

from __future__ import annotations

import pytest

from src.models import Task, ValidationError
from src.storage import export_report, list_tasks


def test_sort_by_priority_orders_by_severity_not_alphabetically():
    """S2 regression: pre-fix this sorted alphabetically (high, low, medium, urgent)."""
    tasks = [
        Task(id=1, title="T-low", priority="low", created_at="2026-01-01"),
        Task(id=2, title="T-urgent", priority="urgent", created_at="2026-01-02"),
        Task(id=3, title="T-medium", priority="medium", created_at="2026-01-03"),
        Task(id=4, title="T-high", priority="high", created_at="2026-01-04"),
    ]
    ordered_ids = [task.id for task in list_tasks(tasks, sort="priority")]
    assert ordered_ids == [2, 4, 3, 1]


def test_sort_by_priority_breaks_ties_by_created_at_then_id():
    """S2 boundary: two tasks tied on priority and created_at; the tie is broken
    deterministically by id, not left to sort() input order."""
    tasks = [
        Task(id=5, title="Medium A", priority="medium", created_at="2026-01-01"),
        Task(id=2, title="Medium B", priority="medium", created_at="2026-01-01"),
    ]
    ordered_ids = [task.id for task in list_tasks(tasks, sort="priority")]
    assert ordered_ids == [2, 5]


def test_sort_by_title_still_case_insensitive_after_priority_fix():
    """S2 neighbour: the untouched title-sort branch of list_tasks keeps working."""
    tasks = [
        Task(id=1, title="banana", created_at="2026-01-01"),
        Task(id=2, title="Apple", created_at="2026-01-02"),
        Task(id=3, title="cherry", created_at="2026-01-03"),
    ]
    titles = [task.title for task in list_tasks(tasks, sort="title")]
    assert titles == ["Apple", "banana", "cherry"]


def test_export_rejects_dot_dot_traversal_and_writes_nothing(tmp_path, sample_tasks):
    """F4 regression: pre-fix this wrote outside export_dir via ``../`` segments."""
    export_dir = tmp_path / "exports"
    with pytest.raises(ValidationError, match="must stay inside the export directory"):
        export_report(sample_tasks, "../escape.txt", export_dir=export_dir)
    assert not (tmp_path / "escape.txt").exists()


def test_export_rejects_absolute_path_escape(tmp_path, sample_tasks):
    """F4 boundary: an absolute filename overrides export_dir when joined by pathlib."""
    export_dir = tmp_path / "exports"
    absolute_target = tmp_path / "outside.txt"
    with pytest.raises(ValidationError, match="must stay inside the export directory"):
        export_report(sample_tasks, str(absolute_target), export_dir=export_dir)
    assert not absolute_target.exists()


def test_export_still_writes_legitimate_nested_filename(tmp_path, sample_tasks):
    """F4 neighbour: a nested-but-contained filename keeps working after the guard
    was added."""
    export_dir = tmp_path / "exports"
    written = export_report(sample_tasks, "sub/dir/report.txt", export_dir=export_dir)
    assert written == export_dir / "sub" / "dir" / "report.txt"
    assert "total: 3" in written.read_text(encoding="utf-8")
