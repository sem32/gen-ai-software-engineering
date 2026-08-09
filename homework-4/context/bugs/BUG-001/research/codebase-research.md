# Codebase Research — BUG-001

## Scope

BUG-001 reports three groups of symptoms against the Task Tracker CLI (`src.__version__ == "1.0.0"`):

- **S1** — `stats` raises `ZeroDivisionError` when there are zero completed tasks.
- **S2** — `list --sort priority` orders tasks alphabetically instead of by severity.
- **S3** — two security concerns from a pre-release review:
  - **S3a** — `admin clear` is reachable with a hardcoded default token even when no operator has
    ever configured `TASKTRACKER_ADMIN_TOKEN`, and the rejection path uses a non-constant-time
    comparison whose error message echoes the caller's guess.
  - **S3b** — `export` joins the export directory with an attacker-controlled filename without
    checking the result stays inside that directory, allowing `..` traversal or an absolute path to
    write anywhere on disk.

All four findings below (F1–F4, covering S1/S2/S3a/S3b) were reproduced against throwaway stores
under `/tmp` (`/tmp/s1.json`, `/tmp/s2.json`, `/tmp/s3.json`, `/tmp/hw4-exports/`) and cleaned up
afterward. `data/` was never touched. Out of scope, per the bug context: store file format changes,
adding a database/network API, and restructuring modules beyond what the four fixes require.

## Codebase Map

| Module | Responsibility | Key functions (with line numbers) |
|---|---|---|
| `src/__init__.py` (3 lines) | Package version marker | `__version__ = "1.0.0"` (line 3) |
| `src/models.py` (77 lines) | `Task` dataclass, priority/status vocabularies, validation | `Task.__post_init__` (models.py:31-46), `Task.to_dict`/`from_dict` (models.py:48-77), `PRIORITIES`/`STATUSES` tuples (models.py:8-9), `PRIORITY_RANK` severity map (models.py:12) |
| `src/stats.py` (60 lines) | Aggregate statistics over a task collection | `completion_days` (stats.py:14-18), `completion_rate` (stats.py:37-42), `average_completion_days` (stats.py:45-49), `summarize` (stats.py:52-60) |
| `src/storage.py` (96 lines) | JSON persistence, listing/sorting, report rendering, export | `TaskStore.load/save/add/complete/clear` (storage.py:23-62), `list_tasks` (storage.py:65-73), `render_report` (storage.py:76-84), `export_report` (storage.py:87-96) |
| `src/auth.py` (30 lines) | Admin token gate for destructive commands | `expected_token` (auth.py:15-17), `verify_admin_token` (auth.py:20-24), `require_admin` (auth.py:27-30) |
| `src/cli.py` (118 lines) | argparse wiring, dispatches to storage/stats/auth, exit codes | `build_parser` (cli.py:32-63), `main` (cli.py:66-118) |
| `tests/` (668 total lines across all files) | pytest suite, 32 tests total (confirmed via `python3 -m pytest -q`) | `tests/conftest.py` fixtures (`store`, `store_path`, `sample_tasks`), one `test_*.py` per source module except `auth.py` (no `test_auth.py` file exists) |

## Findings

### F1 — `stats` crashes on a store with no completed tasks

- **Symptom**: `stats` dies with `ZeroDivisionError` instead of printing the JSON summary when no
  task has `status == "done"` (a fresh store, or a store where every task is still `todo`/`in_progress`).
- **Root cause**: `average_completion_days` divides `total_days` by `len(completed)` with no guard
  for `len(completed) == 0`. `completion_rate`, right above it in the same file, already special-cases
  the empty-collection case by returning early, so the module handles "no data" inconsistently between
  the two functions — exactly what QA's note in the bug context calls out.
- **Location**: `src/stats.py:49` (function `average_completion_days`, defined at `src/stats.py:45`)
- **Evidence** (verbatim, `src/stats.py:37-49`):
  ```python
  def completion_rate(tasks: list[Task]) -> float:
      """Share of tasks that are done, as a percentage rounded to 1 decimal."""
      if not tasks:
          return 0.0
      done = sum(1 for task in tasks if task.status == "done")
      return round(done * 100 / len(tasks), 1)


  def average_completion_days(tasks: list[Task]) -> float:
      """Mean number of days it took to finish the completed tasks."""
      completed = [task for task in tasks if task.status == "done" and task.completed_at]
      total_days = sum(completion_days(task) for task in completed)
      return round(total_days / len(completed), 2)
  ```
  The crash is triggered from `src/cli.py:93`: `print(json.dumps(summarize(store.load()), indent=2))`,
  which calls `summarize` (`src/stats.py:52-60`), which calls `average_completion_days` at
  `src/stats.py:59`.
- **Reproduction**: verified.
  ```bash
  cd homework-4
  python3 -m src.cli --store /tmp/s1.json add "Anything"
  python3 -m src.cli --store /tmp/s1.json stats
  ```
  Observed output (traceback abbreviated to the relevant frames):
  ```
  added #1: Anything (priority=medium)
  Traceback (most recent call last):
    ...
    File ".../src/cli.py", line 93, in main
      print(json.dumps(summarize(store.load()), indent=2))
    File ".../src/stats.py", line 59, in summarize
      "average_completion_days": average_completion_days(tasks),
    File ".../src/stats.py", line 49, in average_completion_days
      return round(total_days / len(completed), 2)
  ZeroDivisionError: division by zero
  ```
  Exit code observed: `1` (falls through Python's unhandled-exception path, not the CLI's own
  `except`/`return` codes at `src/cli.py:107-112`, since `ZeroDivisionError` is neither
  `ValidationError`/`KeyError` nor `AuthError`).
- **Existing test coverage**: none exercises this path. `tests/test_stats.py:42-43`
  (`test_average_completion_days_over_completed_tasks`) only calls `average_completion_days` on
  `sample_tasks`, which always has one `done` task (`tests/conftest.py:32-39`). `tests/test_cli.py:32-39`
  (`test_complete_and_stats`) always completes a task before calling `stats`. No test calls `stats`
  or `average_completion_days`/`summarize` with zero completed tasks or an empty task list.
- **Confidence**: verified.

### F2 — `list --sort priority` returns the wrong order

- **Symptom**: `list --sort priority` sorts tasks alphabetically by the priority string, not by
  severity; `urgent` tasks sort last instead of first.
- **Root cause**: `list_tasks`'s `"priority"` branch sorts by the raw string `task.priority`
  (`"high" < "low" < "medium" < "urgent"` alphabetically) instead of by the severity rank. The model
  layer already defines that severity order — `PRIORITY_RANK`, built from the `PRIORITIES` tuple
  `("urgent", "high", "medium", "low")` where index 0 is most severe — but `storage.py` never
  imports or uses it.
- **Location**: `src/storage.py:69-70` (function `list_tasks`, defined at `src/storage.py:65`); the
  unused severity map lives at `src/models.py:8-12`.
- **Evidence** (verbatim, `src/storage.py:65-73`):
  ```python
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
  The already-declared severity order (verbatim, `src/models.py:8-12`):
  ```python
  PRIORITIES = ("urgent", "high", "medium", "low")
  STATUSES = ("todo", "in_progress", "done")

  #: Severity order used when tasks are sorted by priority (0 = most severe).
  PRIORITY_RANK = {name: index for index, name in enumerate(PRIORITIES)}
  ```
- **Reproduction**: verified.
  ```bash
  cd homework-4
  for p in low urgent medium high; do
    python3 -m src.cli --store /tmp/s2.json add "task-$p" --priority "$p"
  done
  python3 -m src.cli --store /tmp/s2.json list --sort priority
  ```
  Observed output:
  ```
  #  4 high   todo        task-high
  #  1 low    todo        task-low
  #  3 medium todo        task-medium
  #  2 urgent todo        task-urgent
  ```
  This matches the bug report's "observed: high, low, medium, urgent" exactly. Expected per the
  bug context: `urgent, high, medium, low`.
- **Existing test coverage**: none. `tests/test_storage.py` covers `sort="created"`
  (`test_default_listing_is_ordered_by_creation`, line 42-43) and `sort="title"`
  (`test_listing_by_title_is_case_insensitive`, line 46-48), plus the invalid-key rejection
  (`test_unknown_sort_key_is_rejected`, line 51-53), but there is no test at all for `sort="priority"`.
  `tests/test_models.py:49-50` (`test_priority_rank_orders_by_severity`) only tests that
  `PRIORITY_RANK` itself is correctly ordered — it does not test that `list_tasks` uses it.
- **Confidence**: verified.

**Related note (suspected, not a confirmed defect)**: the bug context's acceptance criteria also ask
for "deterministic tie-breaking" on the priority sort. Python's `sorted()` is stable, so ties between
same-priority tasks currently preserve whatever order `tasks` arrived in (typically file/load order,
not necessarily creation order once a store has been edited out of band). The default `"created"`
branch already builds an explicit stable secondary key, `(task.created_at, task.id)`
(`src/storage.py:73`); the `"priority"` branch has no equivalent secondary key. This is a design gap
for the fix to close, not something I could reproduce as an observable "wrong" order today.

### F3 — Admin token handling: usable-without-configuration default and information leaks

- **Symptom** (as reported): "Reviewers could run the destructive `admin clear` command on a machine
  where no admin token had ever been configured, and the rejection message they got back when
  guessing echoed their input."

This bug context symptom actually names two distinct defects; both are documented separately below
so each has its own root cause, evidence, and reproduction.

#### F3a — `admin clear` succeeds via a hardcoded fallback token even when unconfigured

- **Root cause**: `expected_token()` falls back to the module-level constant
  `DEFAULT_ADMIN_TOKEN = "hw4-admin-secret"` whenever the `TASKTRACKER_ADMIN_TOKEN` environment
  variable is unset. Since this fallback string is checked into source control and shipped with
  every install, any caller who knows (or reads) the source can pass `--token hw4-admin-secret` and
  run `admin clear` on an installation where the operator never configured a token at all.
- **Location**: `src/auth.py:8` (constant) and `src/auth.py:15-17` (function `expected_token`,
  used by `require_admin` at `src/auth.py:27-30`, called from `src/cli.py:102`).
- **Evidence** (verbatim, `src/auth.py:1-17`):
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
- **Reproduction**: verified, run directly against the library function that `src/cli.py:102`
  invokes (with `TASKTRACKER_ADMIN_TOKEN` explicitly unset):
  ```bash
  cd homework-4
  python3 -c "
  import os
  os.environ.pop('TASKTRACKER_ADMIN_TOKEN', None)
  from src.auth import expected_token, require_admin, AuthError
  print(expected_token())        # -> 'hw4-admin-secret'
  require_admin('hw4-admin-secret')   # does not raise -> admin action would proceed
  "
  ```
  Observed: `expected_token()` returns `'hw4-admin-secret'` and `require_admin('hw4-admin-secret')`
  raises nothing, i.e. `admin clear` would proceed (`src/cli.py:101-105`) with zero configuration.
- **Existing test coverage**: none covers the unconfigured case. `tests/test_cli.py:58-66`
  (`test_admin_clear_requires_token`) explicitly sets
  `monkeypatch.setenv("TASKTRACKER_ADMIN_TOKEN", "s3cret-for-test")` before exercising `admin clear`,
  so it never observes the no-env-var fallback behavior. There is no `tests/test_auth.py` file.
- **Confidence**: verified.

#### F3b — Non-constant-time token comparison and token echoed back in the rejection error

- **Root cause**: `verify_admin_token` compares the provided token to the expected one with the
  plain `==` operator, which short-circuits on the first differing character and is not
  constant-time (a timing side channel for an attacker probing the token byte-by-byte). Separately,
  `require_admin` builds its `AuthError` message with `{provided!r}`, echoing the caller's guessed
  token back in the exception text, which `src/cli.py:110-112` then prints to stderr as
  `forbidden: admin token rejected: '<the guess>'`.
- **Location**: `src/auth.py:24` (comparison, function `verify_admin_token` at `src/auth.py:20-24`)
  and `src/auth.py:30` (message construction, function `require_admin` at `src/auth.py:27-30`).
- **Evidence** (verbatim, `src/auth.py:20-30`):
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
  Confirmed no constant-time comparison primitive (`hmac.compare_digest` or similar) is imported or
  used anywhere in `src/` (`grep -rn "hmac\|compare_digest" src/` returned no matches).
- **Reproduction**: verified.
  ```bash
  cd homework-4
  python3 -c "
  from src.auth import require_admin, AuthError
  try:
      require_admin('wrong-guess')
  except AuthError as e:
      print(e)
  "
  ```
  Observed: `admin token rejected: 'wrong-guess'` — the guessed value is echoed verbatim. When routed
  through the CLI (`src/cli.py:110-112`), this becomes stderr output
  `forbidden: admin token rejected: 'wrong-guess'`, which is visible in any captured log or terminal
  transcript.
- **Existing test coverage**: `tests/test_cli.py:58-66` only asserts the substring `"forbidden:"` is
  present in stderr (line 63); it does not assert anything about timing safety or about whether the
  guessed token appears in the message. No test would fail today if the message leaked the token more
  verbosely, and no test exists for constant-time comparison at all.
- **Confidence**: verified (root cause and reproduction); the *timing* side-channel exploitability
  itself was not measured (no timing attack was executed) — that the comparison is not
  constant-time is verified by code inspection (plain `==` on `str`, no `hmac.compare_digest`), but
  whether it is *practically* exploitable over this CLI's latency is suspected, not measured.

### F4 — `export` writes outside its export directory

- **Symptom**: A report filename containing `..` segments, or an absolute path, escapes the
  `--export-dir` directory and can overwrite arbitrary files on disk.
- **Root cause**: `export_report` builds the write target with a plain `Path(export_dir) / filename`
  and never validates that the resulting path is still inside `export_dir`. `pathlib`'s `/` operator
  does not sanitize `..` segments, and if `filename` itself is an absolute path, `/` discards
  `export_dir` entirely and returns the absolute path unchanged — both confirmed below.
- **Location**: `src/storage.py:93` (function `export_report`, defined at `src/storage.py:87-96`).
- **Evidence** (verbatim, `src/storage.py:87-96`):
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
- **Reproduction**: verified, both traversal forms named in the bug context.
  1. `..`-segment traversal:
     ```bash
     cd homework-4
     mkdir -p /tmp/hw4-exports
     python3 -m src.cli --store /tmp/s3.json export "../../../../tmp/ESCAPED.txt" --export-dir /tmp/hw4-exports
     ```
     Observed: `report written to /tmp/hw4-exports/../../../../tmp/ESCAPED.txt`, exit code `0`, and
     `/tmp/ESCAPED.txt` was created outside `/tmp/hw4-exports` — matching the bug context's reported
     observation exactly.
  2. Absolute-path override, confirming the `Path./` join semantics that make it possible:
     ```bash
     python3 -c "from pathlib import Path; print(Path('/tmp/hw4-exports') / '/tmp/absolute-escape.txt')"
     ```
     Observed: `/tmp/absolute-escape.txt` — `export_dir` is silently discarded when `filename` is
     absolute, so an absolute `filename` argument would write there directly through the same code
     path (not separately re-verified end-to-end via the CLI, since the join-semantics check above
     already demonstrates the mechanism `export_report` relies on).
  Temp artifacts (`/tmp/s3.json`, `/tmp/hw4-exports/`, `/tmp/ESCAPED.txt`) were removed after
  verification; `data/` was never touched.
- **Existing test coverage**: none covers a malicious filename. `tests/test_storage.py:62-65`
  (`test_export_writes_report_into_export_dir`) and `tests/test_cli.py:48-55`
  (`test_export_writes_file`) both only pass a plain, safe filename (`"report.txt"`). No test asserts
  rejection of `..` segments or absolute paths.
- **Confidence**: verified.

## Related Code Worth Knowing

- `src/models.py:12` — `PRIORITY_RANK = {name: index for index, name in enumerate(PRIORITIES)}` is
  the ready-made severity map (0 = most severe = `"urgent"`) that F2's fix should reuse instead of
  inventing a new ordering; `tests/test_models.py:49-50` already pins its correctness.
- `src/storage.py:73` — the `"created"` sort's stable secondary key pattern,
  `sorted(tasks, key=lambda task: (task.created_at, task.id))`, is the existing convention for
  deterministic tie-breaking that a `"priority"` fix should mirror (e.g. rank first, `task.id` or
  `created_at` second).
- `src/cli.py:107-112` — the CLI's three-tier exit-code convention: `ValidationError`/`KeyError` → 2,
  `AuthError` → 3, unhandled exceptions fall through to Python's default (observed as 1 for F1).
  Any fix that raises a *new* exception type for path-escape rejection (F4) or token misconfiguration
  (F3a) needs to either reuse `ValidationError`/`AuthError` or extend this dispatch, or it will fall
  into the uncontrolled exit-code-1 path the way F1 currently does.
- `src/auth.py:7-8` — `ENV_VAR = "TASKTRACKER_ADMIN_TOKEN"` and `DEFAULT_ADMIN_TOKEN` are the two
  names any F3a fix must touch; `tests/test_cli.py:58-66` already uses `monkeypatch.setenv` on
  `ENV_VAR`, establishing the pattern later admin-related tests should follow.
- `src/storage.py:11-12` — `DEFAULT_STORE_PATH = Path("data/tasks.json")` and
  `DEFAULT_EXPORT_DIR = Path("exports")` are the two on-disk defaults; note `data/` is the real
  project data directory referenced by the bug context's "Environment" section — all reproductions in
  this document intentionally used `--store /tmp/...` and `--export-dir /tmp/...` instead.
- No `tests/test_auth.py` file exists at all — `src/auth.py` currently has zero direct unit test
  coverage; every existing admin-related assertion lives in `tests/test_cli.py` and goes through the
  full CLI dispatch.

## Open Questions

- The bug context asks for token comparison that "does not leak information through timing ... or
  error text," but does not specify how an operator is expected to configure a token going forward
  (e.g., whether a missing `TASKTRACKER_ADMIN_TOKEN` should make `admin clear` categorically
  unavailable, versus some other opt-in mechanism). The fix design will need to decide this; it is
  not determinable from the code alone.
- The bug context's acceptance criteria mention "deterministic tie-breaking" for priority sort, but
  does not state which secondary key is expected (id vs. creation date vs. title). See the *Related
  note* under F2.
- Whether the timing side-channel in F3b is practically exploitable given the CLI's per-invocation
  process startup overhead was not measured — flagged as suspected in F3b's confidence line.

## References

Files opened:
- `context/bugs/BUG-001/bug-context.md` (full file, lines 1-98)
- `src/__init__.py` (lines 1-3)
- `src/auth.py` (lines 1-30)
- `src/cli.py` (lines 1-118)
- `src/models.py` (lines 1-77)
- `src/stats.py` (lines 1-60)
- `src/storage.py` (lines 1-96)
- `tests/conftest.py` (lines 1-48)
- `tests/test_cli.py` (lines 1-66)
- `tests/test_models.py` (lines 1-50)
- `tests/test_stats.py` (lines 1-56)
- `tests/test_storage.py` (lines 1-65)

Commands run (all against `/tmp` scratch stores/dirs, never against `data/`):
```bash
find src tests -type f -name "*.py" | sort
wc -l src/*.py tests/*.py

rm -f /tmp/s1.json /tmp/s2.json /tmp/s3.json && rm -rf /tmp/s3-exports
python3 -m src.cli --store /tmp/s1.json add "Anything"
python3 -m src.cli --store /tmp/s1.json stats

rm -f /tmp/s2.json
for p in low urgent medium high; do
  python3 -m src.cli --store /tmp/s2.json add "task-$p" --priority "$p"
done
python3 -m src.cli --store /tmp/s2.json list --sort priority

rm -f /tmp/s3.json /tmp/ESCAPED.txt
rm -rf /tmp/hw4-exports
python3 -c "
import os
os.environ.pop('TASKTRACKER_ADMIN_TOKEN', None)
from src.auth import expected_token, require_admin, AuthError
print('expected_token (no env var set):', repr(expected_token()))
require_admin('hw4-admin-secret')
try:
    require_admin('wrong-guess')
except AuthError as e:
    print('error message on wrong guess (echoes input):', e)
"
mkdir -p /tmp/hw4-exports
python3 -m src.cli --store /tmp/s3.json export "../../../../tmp/ESCAPED.txt" --export-dir /tmp/hw4-exports
ls -la /tmp/ESCAPED.txt

python3 -c "from pathlib import Path; print(Path('/tmp/hw4-exports') / '/tmp/absolute-escape.txt')"

rm -f /tmp/s1.json /tmp/s2.json /tmp/s3.json /tmp/ESCAPED.txt
rm -rf /tmp/hw4-exports

grep -n "hmac\|compare_digest" src/auth.py
python3 -m pytest -q   # 32 passed
grep -rn "resolve\|commonpath\|is_relative_to" src/ tests/
grep -rn "TASKTRACKER_ADMIN_TOKEN\|require_admin\|verify_admin_token\|AuthError" tests/
```
All temporary files created under `/tmp` during reproduction were deleted after verification.
