"""Baseline tests for the statistics helpers."""

from __future__ import annotations

import pytest

from src.stats import (
    average_completion_days,
    completion_days,
    completion_rate,
    count_by_priority,
    count_by_status,
    summarize,
)


def test_count_by_status_includes_empty_buckets(sample_tasks):
    assert count_by_status(sample_tasks) == {"todo": 1, "in_progress": 1, "done": 1}


def test_count_by_priority_includes_empty_buckets(sample_tasks):
    assert count_by_priority(sample_tasks) == {"urgent": 1, "high": 1, "medium": 0, "low": 1}


def test_completion_rate_is_a_percentage(sample_tasks):
    assert completion_rate(sample_tasks) == 33.3


def test_completion_rate_of_empty_collection_is_zero():
    assert completion_rate([]) == 0.0


def test_completion_days_counts_whole_days(sample_tasks):
    assert completion_days(sample_tasks[0]) == 4


def test_completion_days_rejects_unfinished_task(sample_tasks):
    with pytest.raises(ValueError):
        completion_days(sample_tasks[1])


def test_average_completion_days_over_completed_tasks(sample_tasks):
    assert average_completion_days(sample_tasks) == 4.0


def test_summarize_reports_every_section(sample_tasks):
    summary = summarize(sample_tasks)
    assert summary["total"] == 3
    assert set(summary) == {
        "total",
        "by_status",
        "by_priority",
        "completion_rate_pct",
        "average_completion_days",
    }
