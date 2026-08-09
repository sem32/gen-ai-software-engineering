#!/usr/bin/env python3
"""Optional PostToolUse hook — reminds the agent to re-run the pipeline after touching its code.

Fires after an ``Edit`` or ``Write``. If the edited file belongs to the pipeline, it feeds a short
reminder back into the conversation; otherwise it stays silent. Never blocks anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WATCHED_PREFIXES = ("homework-6/agents/", "homework-6/integrator.py", "homework-6/mcp/")

REMINDER = (
    "Pipeline code changed. Before claiming this works, re-run it and the suite:\n"
    "  cd homework-6 && .venv/bin/python integrator.py\n"
    "  cd homework-6 && .venv/bin/pytest\n"
    "Coverage must stay at or above 80% or the push gate will block."
)


def main() -> int:
    if sys.stdin.isatty():
        return 0
    raw = sys.stdin.read().strip()
    if not raw:
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    file_path = str((payload.get("tool_input") or {}).get("file_path", ""))
    if not file_path:
        return 0

    try:
        relative = Path(file_path).resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        relative = file_path

    if not any(relative.startswith(prefix) for prefix in WATCHED_PREFIXES):
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": REMINDER,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
