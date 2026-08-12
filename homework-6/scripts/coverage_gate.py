#!/usr/bin/env python3
"""Coverage gate — blocks a push when unit-test coverage is below the floor (spec task T-8).

Two ways to run it:

1. **Claude Code hook** (``PreToolUse`` on ``Bash``). The hook payload arrives on stdin; the gate
   only engages when the command being run is a ``git push``. Exit code ``2`` blocks the tool call
   and hands the reason back to the model.

2. **Command line**::

       python scripts/coverage_gate.py               # measure and report
       python scripts/coverage_gate.py --threshold 95
       python scripts/coverage_gate.py --simulate-push   # pretend a push was requested

The same script is what ``scripts/pre-push`` calls, so the git-level and agent-level gates share
one implementation and one threshold.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COVERAGE_JSON = PROJECT_ROOT / "coverage.json"
DEFAULT_THRESHOLD = float(os.environ.get("COVERAGE_MIN", "80"))

GIT_PUSH = re.compile(r"\bgit\b[^|;&]*\bpush\b")

BLOCK_EXIT_CODE = 2  # Claude Code: a PreToolUse hook exiting 2 blocks the call


def pytest_command() -> list[str]:
    """Prefer the project virtualenv so the gate does not depend on the caller's environment."""
    venv_pytest = PROJECT_ROOT / ".venv" / "bin" / "pytest"
    if venv_pytest.exists():
        return [str(venv_pytest)]
    return [sys.executable, "-m", "pytest"]


def run_tests() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*pytest_command(), "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def read_total_coverage() -> float:
    """Total percentage from the ``coverage.json`` report pytest just wrote."""
    if not COVERAGE_JSON.exists():
        raise FileNotFoundError(f"{COVERAGE_JSON} not found — did pytest run?")
    report = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
    return float(report["totals"]["percent_covered"])


def evaluate(threshold: float) -> tuple[bool, str]:
    """Run the suite, compare coverage against the floor and build the human-readable verdict."""
    result = run_tests()
    if result.returncode != 0:
        tail = (result.stdout or result.stderr).strip().splitlines()[-15:]
        return False, "Test suite FAILED — push blocked.\n" + "\n".join(tail)

    coverage = read_total_coverage()
    if coverage < threshold:
        return False, (
            f"Coverage gate FAILED: {coverage:.2f}% < {threshold:g}% required.\n"
            f"Push blocked. Add tests, then run `python scripts/coverage_gate.py` again."
        )
    return True, f"Coverage gate PASSED: {coverage:.2f}% >= {threshold:g}% required."


def hook_payload() -> dict | None:
    """Read the Claude Code hook payload from stdin, if there is one."""
    if sys.stdin.isatty():
        return None
    raw = sys.stdin.read().strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def is_push_command(payload: dict) -> bool:
    if payload.get("tool_name") != "Bash":
        return False
    command = str((payload.get("tool_input") or {}).get("command", ""))
    return bool(GIT_PUSH.search(command))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unit-test coverage gate")
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD, help="minimum total coverage percent"
    )
    parser.add_argument(
        "--simulate-push", action="store_true", help="run the gate as if a push was requested"
    )
    args = parser.parse_args(argv)

    payload = hook_payload()
    gating = args.simulate_push or payload is None or is_push_command(payload)

    if not gating:
        return 0  # not a push — stay out of the way

    passed, message = evaluate(args.threshold)
    if passed:
        print(f"[coverage-gate] {message}")
        return 0

    print(f"[coverage-gate] {message}", file=sys.stderr)
    return BLOCK_EXIT_CODE if payload is not None or args.simulate_push else 1


if __name__ == "__main__":
    raise SystemExit(main())
