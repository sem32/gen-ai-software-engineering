"""Domain model: a single tracked task plus its vocabularies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

PRIORITIES = ("urgent", "high", "medium", "low")
STATUSES = ("todo", "in_progress", "done")

#: Severity order used when tasks are sorted by priority (0 = most severe).
PRIORITY_RANK = {name: index for index, name in enumerate(PRIORITIES)}


class ValidationError(ValueError):
    """Raised when incoming task data does not satisfy the model contract."""


@dataclass
class Task:
    """A unit of work tracked by the application."""

    id: int
    title: str
    priority: str = "medium"
    status: str = "todo"
    created_at: str = ""
    completed_at: str | None = None
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.title = self.title.strip()
        if not self.title:
            raise ValidationError("title must not be empty")
        if self.priority not in PRIORITIES:
            raise ValidationError(
                f"priority must be one of {', '.join(PRIORITIES)}; got {self.priority!r}"
            )
        if self.status not in STATUSES:
            raise ValidationError(
                f"status must be one of {', '.join(STATUSES)}; got {self.status!r}"
            )
        if not self.created_at:
            self.created_at = date.today().isoformat()
        if self.status == "done" and not self.completed_at:
            self.completed_at = date.today().isoformat()

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation of the task."""
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Task":
        """Build a task from stored JSON, rejecting unknown fields."""
        known = {f for f in ("id", "title", "priority", "status", "created_at", "completed_at", "tags")}
        unknown = set(raw) - known
        if unknown:
            raise ValidationError(f"unknown task fields: {', '.join(sorted(unknown))}")
        if "id" not in raw or "title" not in raw:
            raise ValidationError("task requires 'id' and 'title'")
        return cls(
            id=int(raw["id"]),
            title=str(raw["title"]),
            priority=str(raw.get("priority", "medium")),
            status=str(raw.get("status", "todo")),
            created_at=str(raw.get("created_at", "")),
            completed_at=raw.get("completed_at"),
            tags=list(raw.get("tags", [])),
        )
