# Fix Summary — BUG-001

## Overall Status

**COMPLETE.** Baseline `python3 -m pytest` → `32 passed in 0.08s`. All five planned changes were
applied exactly as specified, in the plan's execution order, with the full suite re-run after each
one. Final `python3 -m pytest` → `32 passed in 0.08s`.

## Changes Made

### Change 1 — `average_completion_days` returns 0.0 when nothing is completed (plan change 1, defect S1)

- **File**: `src/stats.py`
- **Location**: function `average_completion_days`, lines `45-54` after the edit
- **Before**:
  ```python
  def average_completion_days(tasks: list[Task]) -> float:
      """Mean number of days it took to finish the completed tasks."""
      completed = [task for task in tasks if task.status == "done" and task.completed_at]
      total_days = sum(completion_days(task) for task in completed)
      return round(total_days / len(completed), 2)
  ```
- **After**:
  ```python
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
  ```
- **Test result**: `python3 -m pytest` → `32 passed in 0.08s`

### Change 2 — sort by severity rank with a deterministic tie-break (plan change 2 (2a+2b), defect S2)

- **File**: `src/storage.py`
- **Location**: module import (line `9`) and function `list_tasks`, lines `65-75` after the edit
- **Before**:
  ```python
  from .models import Task, ValidationError
  ...
  def list_tasks(tasks: list[Task], sort: str = "created") -> list[Task]:
      """Return tasks ordered by the requested sort key."""
      if sort not in SORT_KEYS:
          raise ValidationError(f"sort must be one of {', '.join(SORT_KEYS)}; got {sort!r}")
      if sort == "priority":
          return sorted(tasks, key=lambda task: task.priority)
      if sort == "title":
          return sorted(tasks, key=lambda task: task.title.lower())
      return sorted(tasks, key=lambda task: (task.created_at, task.id))
  ```
- **After**:
  ```python
  from .models import PRIORITY_RANK, Task, ValidationError
  ...
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
  ```
- **Test result**: `python3 -m pytest` → `32 passed in 0.08s` (both sub-steps 2a and 2b applied
  together before this run, as the plan's ordering notes required)

### Change 3 — no usable admin token unless one is configured (plan change 3, defect S3a)

- **File**: `src/auth.py`
- **Location**: module header and function `expected_token`, lines `1-23` after the edit
- **Before**:
  ```python
  """Token check guarding the destructive ``admin`` sub-commands."""

  from __future__ import annotations

  import os

  ENV_VAR = "TASKTRACKER_ADMIN_TOKEN"
  DEFAULT_ADMIN_TOKEN = "hw4-admin-secret"


  class AuthError(Exception):
      """Raised when an admin action is attempted without a valid token."""


  def expected_token() -> str:
      """Return the admin token this installation expects."""
      return os.environ.get(ENV_VAR, DEFAULT_ADMIN_TOKEN)
  ```
- **After**:
  ```python
  """Token check guarding the destructive ``admin`` sub-commands."""

  from __future__ import annotations

  import hmac
  import os

  ENV_VAR = "TASKTRACKER_ADMIN_TOKEN"


  class AuthError(Exception):
      """Raised when an admin action is attempted without a valid token."""


  def expected_token() -> str:
      """Return the admin token this installation expects.

      Raises :class:`AuthError` when no token is configured: there is no built-in
      default, so admin commands stay unavailable until an operator sets the
      environment variable.
      """
      configured = os.environ.get(ENV_VAR, "")
      if not configured:
          raise AuthError(f"admin commands are disabled: {ENV_VAR} is not configured")
      return configured
  ```
- **Test result**: `python3 -m pytest` → `32 passed in 0.08s`

### Change 4 — constant-time comparison and a non-echoing rejection (plan change 4, defect S3b)

- **File**: `src/auth.py`
- **Location**: functions `verify_admin_token` and `require_admin`, lines `26-39` after the edit
- **Before**:
  ```python
  def verify_admin_token(provided: str | None) -> bool:
      """Return True when ``provided`` matches the configured admin token."""
      if provided is None:
          return False
      return provided == expected_token()


  def require_admin(provided: str | None) -> None:
      """Raise :class:`AuthError` unless ``provided`` is the admin token."""
      if not verify_admin_token(provided):
          raise AuthError(f"admin token rejected: {provided!r}")
  ```
- **After**:
  ```python
  def verify_admin_token(provided: str | None) -> bool:
      """Return True when ``provided`` matches the configured admin token.

      The comparison is constant-time. Raises :class:`AuthError` when no admin
      token is configured for this installation.
      """
      expected = expected_token()
      if provided is None:
          return False
      return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


  def require_admin(provided: str | None) -> None:
      """Raise :class:`AuthError` unless ``provided`` is the admin token."""
      if not verify_admin_token(provided):
          raise AuthError("admin token rejected")
  ```
- **Test result**: `python3 -m pytest` → `32 passed in 0.08s`

### Change 5 — `export` rejects filenames that escape the export directory (plan change 5, defect S3.2 / F4)

- **File**: `src/storage.py`
- **Location**: function `export_report`, lines `90-108` after the edit
- **Before**:
  ```python
  def export_report(
      tasks: list[Task],
      filename: str,
      export_dir: Path | str = DEFAULT_EXPORT_DIR,
  ) -> Path:
      """Write a task report under ``export_dir`` and return the written path."""
      target = Path(export_dir) / filename
      target.parent.mkdir(parents=True, exist_ok=True)
      target.write_text(render_report(tasks), encoding="utf-8")
      return target
  ```
- **After**:
  ```python
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
  ```
- **Test result**: `python3 -m pytest` → `32 passed in 0.08s`

## Final Verification

- **Final full-suite run**: `python3 -m pytest` → `32 passed in 0.08s`

## Changed Files

| File | Functions touched | Defect(s) addressed |
|---|---|---|
| `src/stats.py` | `average_completion_days` | S1 — `stats` crashed with `ZeroDivisionError` when no tasks were completed |
| `src/storage.py` | module import (line 9), `list_tasks`, `export_report` | S2 — `list --sort priority` sorted alphabetically instead of by severity; S3.2/F4 — `export` allowed path traversal / absolute-path escape out of the export directory |
| `src/auth.py` | module header (`DEFAULT_ADMIN_TOKEN` removed, `import hmac` added), `expected_token`, `verify_admin_token`, `require_admin` | S3a — hardcoded fallback admin token allowed `admin clear` on any unconfigured install; S3b — token comparison was not constant-time and the rejection error echoed the caller's supplied token |

## Deviations From Plan

None. All five changes were applied verbatim as specified, in the plan's execution order (1 → 2(2a+2b) → 3 → 4 → 5), with the two stated couplings honored (2a and 2b applied together in a single step; Change 3 applied before Change 4 so `import hmac` exists before it is used). No test file, `src/cli.py`, `src/models.py`, or `src/__init__.py` was touched, matching the plan's declared scope.

## Manual Verification

All commands below were run against `/tmp` scratch paths only; `data/` was never touched. Each block was executed during this run and produced the output shown.

**S1 — `stats` on a store with a task but zero completed tasks:**
```bash
python3 -m src.cli --store /tmp/b1.json add "Anything"
python3 -m src.cli --store /tmp/b1.json stats
```
Expected/observed: exit `0`, JSON payload with `"average_completion_days": 0.0` and `"completion_rate_pct": 0.0` (no traceback).

**S2 — `list --sort priority` orders by severity with deterministic tie-break:**
```bash
for p in low urgent medium high; do
  python3 -m src.cli --store /tmp/b2.json add "task-$p" --priority "$p"
done
python3 -m src.cli --store /tmp/b2.json list --sort priority
```
Expected/observed: tasks printed in order `urgent, high, medium, low` (not alphabetical).

**S3a — `admin clear` is impossible without a configured token:**
```bash
env -u TASKTRACKER_ADMIN_TOKEN python3 -m src.cli --store /tmp/b3.json admin clear --token hw4-admin-secret
echo "exit=$?"
```
Expected/observed: stderr `forbidden: admin commands are disabled: TASKTRACKER_ADMIN_TOKEN is not configured`, `exit=3`. The former hardcoded token `hw4-admin-secret` no longer works.

**S3b — rejection message does not echo the supplied token** (verified by code inspection and by the
absence of any `{provided!r}` interpolation in `require_admin`; also implicitly covered by the S3a
command above, whose error message names only the missing configuration, never the `--token` value
passed):
```bash
grep -n "admin token rejected" src/auth.py
```
Expected/observed: single plain string literal `"admin token rejected"` with no f-string interpolation.

**F4 — `export` refuses a traversing filename and writes nothing:**
```bash
python3 -m src.cli --store /tmp/b3.json export "../../../../tmp/ESCAPED.txt" --export-dir /tmp/b-exports
echo "exit=$?"
ls -la /tmp/ESCAPED.txt
```
Expected/observed: stderr `error: export filename must stay inside the export directory; got '../../../../tmp/ESCAPED.txt'`, `exit=2`, and `ls` reports `/tmp/ESCAPED.txt: No such file or directory` (nothing was written).

**Regression gate — full suite:**
```bash
python3 -m pytest
```
Expected/observed: `32 passed in 0.08s`.

Cleanup performed after verification: `rm -f /tmp/b1.json /tmp/b2.json /tmp/b3.json; rm -rf /tmp/b-exports`.

## References

- Plan sections executed: `## Changes` (Change 1 through Change 5), `## Execution Order` (steps 1-5)
  in `context/bugs/BUG-001/implementation-plan.md`
- Files edited: `src/stats.py`, `src/storage.py`, `src/auth.py`
- Commands run: `python3 -m pytest` (six times — baseline plus once after each of the five changes,
  all `32 passed in 0.08s`); the manual smoke-check block under *Manual Verification* above
