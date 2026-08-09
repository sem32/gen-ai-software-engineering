"""JSON-file persistence, listing and report export for tasks."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import PRIORITY_RANK, Task, ValidationError

DEFAULT_STORE_PATH = Path("data/tasks.json")
DEFAULT_EXPORT_DIR = Path("exports")

SORT_KEYS = ("created", "priority", "title")


class TaskStore:
    """A tiny JSON-backed collection of tasks."""

    def __init__(self, path: Path | str = DEFAULT_STORE_PATH) -> None:
        self.path = Path(path)

    def load(self) -> list[Task]:
        """Read all tasks from disk; an absent store is an empty store."""
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        if not isinstance(raw, list):
            raise ValidationError("store file must contain a JSON array of tasks")
        return [Task.from_dict(item) for item in raw]

    def save(self, tasks: list[Task]) -> None:
        """Write all tasks to disk, creating parent directories as needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [task.to_dict() for task in tasks]
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def add(self, title: str, priority: str = "medium", tags: list[str] | None = None) -> Task:
        """Append a new task and persist the store."""
        tasks = self.load()
        next_id = max((task.id for task in tasks), default=0) + 1
        task = Task(id=next_id, title=title, priority=priority, tags=list(tags or []))
        tasks.append(task)
        self.save(tasks)
        return task

    def complete(self, task_id: int) -> Task:
        """Mark a task as done and persist the store."""
        tasks = self.load()
        for task in tasks:
            if task.id == task_id:
                task.status = "done"
                task.completed_at = task.completed_at or date.today().isoformat()
                self.save(tasks)
                return task
        raise KeyError(f"no task with id {task_id}")

    def clear(self) -> int:
        """Delete every task; returns how many were removed."""
        tasks = self.load()
        self.save([])
        return len(tasks)


def list_tasks(tasks: list[Task], sort: str = "created") -> list[Task]:
    """Return tasks ordered by the requested sort key."""
    if sort not in SORT_KEYS:
        raise ValidationError(f"sort must be one of {', '.join(SORT_KEYS)}; got {sort!r}")
    if sort == "priority":
        return sorted(
            tasks,
            key=lambda task: (PRIORITY_RANK[task.priority], task.created_at, task.id),
        )
    if sort == "title":
        return sorted(tasks, key=lambda task: task.title.lower())
    return sorted(tasks, key=lambda task: (task.created_at, task.id))


def render_report(tasks: list[Task]) -> str:
    """Render a plain-text report of the given tasks."""
    lines = ["# Task report", f"total: {len(tasks)}", ""]
    for task in tasks:
        lines.append(
            f"- [{task.status}] #{task.id} {task.title} "
            f"(priority={task.priority}, created={task.created_at})"
        )
    return "\n".join(lines) + "\n"


def export_report(
    tasks: list[Task],
    filename: str,
    export_dir: Path | str = DEFAULT_EXPORT_DIR,
) -> Path:
    """Write a task report under ``export_dir`` and return the written path.

    ``filename`` must resolve to a location inside ``export_dir``; ``..``
    segments and absolute paths are rejected before anything is written.
    """
    base = Path(export_dir)
    target = base / filename
    if base.resolve() not in target.resolve().parents:
        raise ValidationError(
            f"export filename must stay inside the export directory; got {filename!r}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_report(tasks), encoding="utf-8")
    return target
