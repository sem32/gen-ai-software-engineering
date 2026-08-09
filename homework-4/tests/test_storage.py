"""Baseline tests for persistence, listing and report rendering."""

from __future__ import annotations

import pytest

from src.models import ValidationError
from src.storage import TaskStore, export_report, list_tasks, render_report


def test_missing_store_reads_as_empty(store: TaskStore):
    assert store.load() == []


def test_add_assigns_incrementing_ids_and_persists(store: TaskStore):
    first = store.add("First", priority="high")
    second = store.add("Second")
    assert (first.id, second.id) == (1, 2)
    assert [task.title for task in TaskStore(store.path).load()] == ["First", "Second"]


def test_complete_marks_task_done(store: TaskStore):
    store.add("Finish me")
    task = store.complete(1)
    assert task.status == "done"
    assert task.completed_at
    assert store.load()[0].status == "done"


def test_complete_unknown_id_raises(store: TaskStore):
    with pytest.raises(KeyError):
        store.complete(99)


def test_clear_removes_every_task(store: TaskStore):
    store.add("One")
    store.add("Two")
    assert store.clear() == 2
    assert store.load() == []


def test_default_listing_is_ordered_by_creation(sample_tasks):
    assert [task.id for task in list_tasks(sample_tasks)] == [1, 2, 3]


def test_listing_by_title_is_case_insensitive(sample_tasks):
    titles = [task.title for task in list_tasks(sample_tasks, sort="title")]
    assert titles == ["Answer support ticket", "Ship the release", "Update the changelog"]


def test_unknown_sort_key_is_rejected(sample_tasks):
    with pytest.raises(ValidationError):
        list_tasks(sample_tasks, sort="deadline")


def test_report_lists_every_task(sample_tasks):
    report = render_report(sample_tasks)
    assert "total: 3" in report
    assert "#1 Ship the release" in report


def test_export_writes_report_into_export_dir(tmp_path, sample_tasks):
    written = export_report(sample_tasks, "report.txt", export_dir=tmp_path / "exports")
    assert written == tmp_path / "exports" / "report.txt"
    assert "total: 3" in written.read_text(encoding="utf-8")
