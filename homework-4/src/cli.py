"""Command-line interface for the Task Tracker application.

Usage examples::

    python -m src.cli add "Write the report" --priority high --tag docs
    python -m src.cli list --sort priority
    python -m src.cli complete 1
    python -m src.cli stats
    python -m src.cli export report.txt
    python -m src.cli admin clear --token "$TASKTRACKER_ADMIN_TOKEN"
"""

from __future__ import annotations

import argparse
import json
import sys

from .auth import AuthError, require_admin
from .models import PRIORITIES, ValidationError
from .storage import (
    DEFAULT_EXPORT_DIR,
    DEFAULT_STORE_PATH,
    SORT_KEYS,
    TaskStore,
    export_report,
    list_tasks,
)
from .stats import summarize


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(prog="task-tracker", description="Track small units of work.")
    parser.add_argument(
        "--store",
        default=str(DEFAULT_STORE_PATH),
        help=f"path to the JSON store (default: {DEFAULT_STORE_PATH})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="add a task")
    add.add_argument("title")
    add.add_argument("--priority", choices=PRIORITIES, default="medium")
    add.add_argument("--tag", action="append", dest="tags", default=[])

    listing = subparsers.add_parser("list", help="list tasks")
    listing.add_argument("--sort", choices=SORT_KEYS, default="created")

    complete = subparsers.add_parser("complete", help="mark a task as done")
    complete.add_argument("task_id", type=int)

    subparsers.add_parser("stats", help="print aggregate statistics")

    export = subparsers.add_parser("export", help="export a text report")
    export.add_argument("filename")
    export.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))

    admin = subparsers.add_parser("admin", help="destructive maintenance commands")
    admin.add_argument("action", choices=["clear"])
    admin.add_argument("--token", default=None, help="admin token")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one CLI command; returns the process exit code."""
    args = build_parser().parse_args(argv)
    store = TaskStore(args.store)

    try:
        if args.command == "add":
            task = store.add(args.title, priority=args.priority, tags=args.tags)
            print(f"added #{task.id}: {task.title} (priority={task.priority})")
            return 0

        if args.command == "list":
            tasks = list_tasks(store.load(), sort=args.sort)
            if not tasks:
                print("no tasks yet")
                return 0
            for task in tasks:
                tags = f" [{', '.join(task.tags)}]" if task.tags else ""
                print(f"#{task.id:>3} {task.priority:<6} {task.status:<11} {task.title}{tags}")
            return 0

        if args.command == "complete":
            task = store.complete(args.task_id)
            print(f"completed #{task.id}: {task.title}")
            return 0

        if args.command == "stats":
            print(json.dumps(summarize(store.load()), indent=2))
            return 0

        if args.command == "export":
            path = export_report(store.load(), args.filename, export_dir=args.export_dir)
            print(f"report written to {path}")
            return 0

        if args.command == "admin":
            require_admin(args.token)
            removed = store.clear()
            print(f"cleared {removed} task(s)")
            return 0

    except (ValidationError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except AuthError as exc:
        print(f"forbidden: {exc}", file=sys.stderr)
        return 3

    return 1


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
