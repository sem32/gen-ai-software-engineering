# Implementation Plan — BUG-001

## Source

- **Verified research**: `context/bugs/BUG-001/research/verified-research.md`
- **Verdict**: `PASS` — **Research Quality B (`RELIABLE`)** (D1 = 97.36%, D2 = 100%, D3 = `COMPLETE`)
- **Gate decision**: the verifier explicitly states *"The Bug Planner may proceed"*, substituting the
  corrected references from *Discrepancies Found* for the original research claims.

Corrected references used in place of the original research values:

| ID | Original claim | Corrected reference used here |
|---|---|---|
| D-1 | `main` spans `src/cli.py:66-118` | **`main` spans `src/cli.py:66-114`**; `src/cli.py:117-118` is the `__main__` entry point |
| D-2 | `tests/test_stats.py` lines 1-56 | **`tests/test_stats.py` lines 1-55** |
| D-3 | `tests/` is 668 lines | **`tests/` is 284 lines** across 5 files (668 = `src/` 384 + `tests/` 284) |

None of the three discrepancies touches a fix site. Every fix-bearing reference in this plan
(`src/stats.py:45-49`, `src/storage.py:9,65-73,87-96`, `src/auth.py:5-8,15-30`) was independently
verified as exact, and all six quoted research snippets matched the source character-for-character.

**Additional planner verification** (run in this session, read-only): every "Before" snippet below was
re-read from the live source at the cited lines, and the export-containment logic in Change 5 was
prototyped standalone to confirm it rejects `..` and absolute filenames while preserving the exact
return value the existing test asserts (see *Design Decisions*, row 5b).

## Acceptance Criteria

Copied from `context/bugs/BUG-001/bug-context.md:86-91`:

- [ ] `stats` succeeds on a store with zero tasks and on a store with no completed tasks. → **Change 1**
- [ ] `list --sort priority` returns `urgent → high → medium → low`, with deterministic tie-breaking. → **Change 2**
- [ ] `admin clear` is impossible unless an admin token is explicitly configured in the environment. → **Change 3**
- [ ] Token comparison is constant-time and error messages do not echo the supplied token. → **Change 4**
- [ ] `export` refuses any filename that resolves outside the export directory, writing nothing. → **Change 5**
- [ ] The existing suite (32 tests) still passes; no public CLI flags are renamed or removed. → **all changes; verified after each**

## Design Decisions

| # | Decision | Chosen approach | Alternative rejected | Why |
|---|---|---|---|---|
| 1 | Neutral value for `average_completion_days` with zero completed tasks | Early `return 0.0` on an empty `completed` list | Return `None`, or `float("nan")` | `completion_rate` at `src/stats.py:39-40` already returns `0.0` for the empty case. The bug context (line 38-39) explicitly complains that "the two functions disagree about how 'no data' is represented", so matching the existing convention is the fix. `None`/`NaN` would also change the JSON payload shape (`null`/`NaN` is not valid JSON for `NaN`). |
| 2 | Severity ordering source | Import the existing `PRIORITY_RANK` from `src/models.py:12` into `src/storage.py` | Define a new local rank map, or reorder the `PRIORITIES` tuple | `PRIORITY_RANK` already exists, is documented as "0 = most severe" (`src/models.py:11`), and is already asserted by `tests/test_models.py:49-50`. Reordering `PRIORITIES` would change the `--priority` choice order in `--help` and the `by_priority` key order in `stats` output — out of scope. |
| 3 | Priority tie-break | `(PRIORITY_RANK[task.priority], task.created_at, task.id)` | Rely on `sorted()` stability alone | The acceptance criterion demands "deterministic tie-breaking". `(task.created_at, task.id)` is the codebase's existing tie-break convention at `src/storage.py:73`; reusing it keeps the two branches consistent. `PRIORITY_RANK[...]` cannot `KeyError` because `Task.__post_init__` (`src/models.py:35-38`) rejects any priority outside `PRIORITIES`. |
| 4a | Removing the fallback admin token | Delete `DEFAULT_ADMIN_TOKEN` entirely; `expected_token()` raises `AuthError` when `TASKTRACKER_ADMIN_TOKEN` is unset or empty | Keep the constant but set it to `None`/`""` | Leaving any literal token in source keeps a shipped secret in the repo. `DEFAULT_ADMIN_TOKEN` is referenced nowhere else (`grep` over `src/` and `tests/` finds only its own definition line), so deleting it breaks no caller and no test. Treating an empty-string env var as "unconfigured" closes the `TASKTRACKER_ADMIN_TOKEN= ` bypass. |
| 4b | Error type for "not configured" | Reuse `AuthError` | Introduce a new `ConfigError` exception | `AuthError` is already caught at `src/cli.py:110-112` → exit code **3**. A new exception type would fall through to the unhandled path (exit 1) unless `cli.py` were also edited — a larger change for no behavioural gain. A distinct *message* (not a distinct type) gives the operator the clarity they need. |
| 4c | Where the "not configured" check fires | At the top of `verify_admin_token`, before the `provided is None` check | After the `provided is None` check | Otherwise `admin clear` with no `--token` on an unconfigured machine returns the generic "rejected" message instead of telling the operator the install is unconfigured. Checking first makes the message depend only on installation state, never on the caller's input. |
| 4d | Constant-time comparison | `hmac.compare_digest` on UTF-8 **bytes** | `hmac.compare_digest` on `str` | `compare_digest` raises `TypeError` for `str` arguments containing non-ASCII characters. Encoding both sides to `bytes` first makes any token value safe. `hmac` is stdlib; the research confirmed nothing in `src/` imports it yet, so this is a new import. |
| 4e | Rejection message | `AuthError("admin token rejected")` — no interpolation | Redact partially, e.g. show the first 2 chars | The acceptance criterion is "error messages do not echo the supplied token". Any partial echo is still a leak. The message keeps the `"admin token rejected"` prefix so the existing `assert "forbidden:" in err` (`tests/test_cli.py:63`) and human-facing wording stay recognisable. |
| 5a | Error type for a traversing export filename | Reuse `ValidationError` | New `ExportError`, or `AuthError` | `ValidationError` is already imported in `src/storage.py:9`, is already the module's rejection type for bad input (`src/storage.py:29,68`), and is already caught at `src/cli.py:107-109` → exit code **2** (non-zero, as the criterion requires) with an `error: ...` message. No `cli.py` edit needed. |
| 5b | Containment check shape | Compare `Path(export_dir).resolve()` against `(Path(export_dir) / filename).resolve()` via `resolved_base in resolved_target.parents`, but **return the unresolved `target`** | Return the resolved path; or use `target.is_relative_to(base)` | Returning the resolved path **breaks an existing test**: on macOS `tmp_path` is `/var/folders/...` while `resolve()` yields `/private/var/folders/...`, so `written == tmp_path / "exports" / "report.txt"` (`tests/test_storage.py:64`) would fail. Verified by prototype. The `in .parents` form is preferred over `is_relative_to` because it also rejects `filename` values that resolve to the export directory itself (`""`, `"."`), which `is_relative_to` would accept. |
| 5c | Order of validation vs. write | Validate before `mkdir`/`write_text` | Write then check | The criterion says "writing nothing". Raising before `target.parent.mkdir(...)` guarantees no directory and no file is created on the rejection path. |
| 6 | Scope | No changes to `src/cli.py`, `src/models.py`, `src/__init__.py`, or any test file | Adding CLI flags / restructuring | Every criterion is satisfiable inside `stats.py`, `storage.py` and `auth.py`. `bug-context.md:96` puts restructuring out of scope, and test authoring belongs to a later pipeline agent. |

## Changes

### Change 1 — `average_completion_days` returns 0.0 when nothing is completed (defect S1)

- **File**: `src/stats.py`
- **Location**: function `average_completion_days`, lines `45-49`
- **Before**:
  ```python
  45  def average_completion_days(tasks: list[Task]) -> float:
  46      """Mean number of days it took to finish the completed tasks."""
  47      completed = [task for task in tasks if task.status == "done" and task.completed_at]
  48      total_days = sum(completion_days(task) for task in completed)
  49      return round(total_days / len(completed), 2)
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
- **Rationale**: `src/stats.py:49` divided by `len(completed)` with no zero guard, so `summarize`
  (`src/stats.py:59`) raised `ZeroDivisionError` up through `src/cli.py:93`, which catches only
  `ValidationError`/`KeyError`/`AuthError` (`src/cli.py:107-112`) and therefore exited `1` with a
  traceback. The guard mirrors `completion_rate`'s existing `if not tasks: return 0.0`
  (`src/stats.py:39-40`), so both functions now represent "no data" the same way. This also covers
  the zero-task store, because an empty `tasks` list yields an empty `completed` list.
  `tests/test_stats.py:42-43` (`== 4.0` on `sample_tasks`, which has one completed task) is
  unaffected, and the `summarize` key set asserted at `tests/test_stats.py:49-55` is unchanged.
- **Verify**: `python3 -m pytest` (expect: 32 passed)

### Change 2 — sort by severity rank with a deterministic tie-break (defect S2)

Two sub-steps in the same file: the import, then the sort branch. Apply both before running the
suite — the import alone is inert and the branch alone would raise `NameError`.

#### 2a — import the existing severity map

- **File**: `src/storage.py`
- **Location**: module imports, line `9`
- **Before**:
  ```python
  9  from .models import Task, ValidationError
  ```
- **After**:
  ```python
  from .models import PRIORITY_RANK, Task, ValidationError
  ```
- **Rationale**: `src/storage.py` never imported `PRIORITY_RANK`; the map already exists at
  `src/models.py:12` and is documented as "0 = most severe" (`src/models.py:11`). Names are kept in
  alphabetical order, matching the existing import style in this file and in `src/cli.py:21-28`.

#### 2b — use the rank in the `"priority"` branch

- **File**: `src/storage.py`
- **Location**: function `list_tasks`, lines `65-73` (edit targets line `70`)
- **Before**:
  ```python
  65  def list_tasks(tasks: list[Task], sort: str = "created") -> list[Task]:
  66      """Return tasks ordered by the requested sort key."""
  67      if sort not in SORT_KEYS:
  68          raise ValidationError(f"sort must be one of {', '.join(SORT_KEYS)}; got {sort!r}")
  69      if sort == "priority":
  70          return sorted(tasks, key=lambda task: task.priority)
  71      if sort == "title":
  72          return sorted(tasks, key=lambda task: task.title.lower())
  73      return sorted(tasks, key=lambda task: (task.created_at, task.id))
  ```
- **After**:
  ```python
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
- **Rationale**: `src/storage.py:70` sorted by the raw string, giving alphabetical order
  (`high, low, medium, urgent`) instead of severity order. `PRIORITY_RANK` maps
  `urgent→0, high→1, medium→2, low→3`, so ascending sort on the rank yields
  `urgent → high → medium → low` as the acceptance criterion requires. The `(created_at, id)`
  tail reuses the tie-break convention already at `src/storage.py:73`, satisfying "deterministic
  tie-breaking". The lookup is total: `Task.__post_init__` (`src/models.py:35-38`) raises
  `ValidationError` for any priority outside `PRIORITIES`, so no `KeyError` is reachable. The
  `"title"`, `"created"` and invalid-key branches are untouched, so
  `tests/test_storage.py:42-43,46-48,51-53` keep passing.
- **Verify**: `python3 -m pytest` (expect: 32 passed)

### Change 3 — no usable admin token unless one is configured (defect S3a)

- **File**: `src/auth.py`
- **Location**: module header and function `expected_token`, lines `1-17`
- **Before**:
  ```python
   1  """Token check guarding the destructive ``admin`` sub-commands."""
   2
   3  from __future__ import annotations
   4
   5  import os
   6
   7  ENV_VAR = "TASKTRACKER_ADMIN_TOKEN"
   8  DEFAULT_ADMIN_TOKEN = "hw4-admin-secret"
   9
  10
  11  class AuthError(Exception):
  12      """Raised when an admin action is attempted without a valid token."""
  13
  14
  15  def expected_token() -> str:
  16      """Return the admin token this installation expects."""
  17      return os.environ.get(ENV_VAR, DEFAULT_ADMIN_TOKEN)
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
- **Exact new behaviour the executor must copy verbatim**:
  - `DEFAULT_ADMIN_TOKEN` is **deleted** (the whole of line 8).
  - `import hmac` is added above `import os` (alphabetical, stdlib group) — it is used by Change 4.
  - New error message string, exactly: `f"admin commands are disabled: {ENV_VAR} is not configured"`,
    which renders as `admin commands are disabled: TASKTRACKER_ADMIN_TOKEN is not configured` and
    reaches the user as `forbidden: admin commands are disabled: TASKTRACKER_ADMIN_TOKEN is not configured`
    on stderr with exit code **3** (via `src/cli.py:110-112`).
  - No new exception class is introduced; `AuthError` is reused.
- **Rationale**: `src/auth.py:17` fell back to the literal `"hw4-admin-secret"`, so on any machine
  where `TASKTRACKER_ADMIN_TOKEN` was never set, anyone who read the source could run the destructive
  `admin clear` path (`src/cli.py:101-105`). Removing the constant and raising instead makes the
  command impossible until the operator configures a token. Treating `""` as unconfigured (rather
  than `os.environ.get(ENV_VAR) is None`) also closes the empty-value variant, where an exported but
  blank variable would otherwise make the empty string a valid token.
  `tests/test_cli.py:58-66` sets the variable via `monkeypatch.setenv`, so it never reaches this
  branch and keeps passing.
- **Verify**: `python3 -m pytest` (expect: 32 passed)

### Change 4 — constant-time comparison and a non-echoing rejection (defect S3b)

- **File**: `src/auth.py`
- **Location**: functions `verify_admin_token` (lines `20-24`) and `require_admin` (lines `27-30`)
- **Before**:
  ```python
  20  def verify_admin_token(provided: str | None) -> bool:
  21      """Return True when ``provided`` matches the configured admin token."""
  22      if provided is None:
  23          return False
  24      return provided == expected_token()
  25
  26
  27  def require_admin(provided: str | None) -> None:
  28      """Raise :class:`AuthError` unless ``provided`` is the admin token."""
  29      if not verify_admin_token(provided):
  30          raise AuthError(f"admin token rejected: {provided!r}")
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
- **Exact new behaviour the executor must copy verbatim**:
  - Rejection message string, exactly: `"admin token rejected"` — a plain string literal, **not** an
    f-string, and with no reference to `provided`. It reaches the user as
    `forbidden: admin token rejected` on stderr with exit code **3**.
  - `expected_token()` is called **before** the `provided is None` check, so an unconfigured
    installation reports the Change-3 message regardless of what the caller passed.
- **Rationale**: `src/auth.py:24` used `==`, which short-circuits on the first differing byte and
  therefore leaks the length of the matching prefix through timing; `hmac.compare_digest` compares in
  time independent of the contents. Encoding both operands to UTF-8 bytes avoids the `TypeError`
  `compare_digest` raises for non-ASCII `str` arguments. `src/auth.py:30` interpolated `{provided!r}`
  into the error, which `src/cli.py:110-112` printed verbatim to stderr (verified:
  `forbidden: admin token rejected: 'wrong-guess'`) — that echo is removed. The `"admin token
  rejected"` prefix is preserved so `assert "forbidden:" in err` (`tests/test_cli.py:63`) still holds
  and the wording stays familiar. `hmac` is imported in Change 3.
- **Verify**: `python3 -m pytest` (expect: 32 passed)

### Change 5 — `export` rejects filenames that escape the export directory (defect S3.2 / F4)

- **File**: `src/storage.py`
- **Location**: function `export_report`, lines `87-96`
- **Before**:
  ```python
  87  def export_report(
  88      tasks: list[Task],
  89      filename: str,
  90      export_dir: Path | str = DEFAULT_EXPORT_DIR,
  91  ) -> Path:
  92      """Write a task report under ``export_dir`` and return the written path."""
  93      target = Path(export_dir) / filename
  94      target.parent.mkdir(parents=True, exist_ok=True)
  95      target.write_text(render_report(tasks), encoding="utf-8")
  96      return target
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
- **Exact new behaviour the executor must copy verbatim**:
  - New error message string, exactly:
    `f"export filename must stay inside the export directory; got {filename!r}"`. For the reported
    reproduction it renders as
    `export filename must stay inside the export directory; got '../../../../tmp/ESCAPED.txt'` and
    reaches the user as `error: export filename must stay inside the export directory; got '...'`
    on stderr with exit code **2** (via `src/cli.py:107-109`).
  - The exception type is the **existing** `ValidationError`, already imported at `src/storage.py:9`
    (Change 2a extends that same import line — both edits must be present together).
  - The function still returns the **unresolved** `target`, i.e. `Path(export_dir) / filename`.
- **Rationale**: `src/storage.py:93` joined `export_dir` and `filename` with no containment check, so
  `..` segments escaped the directory and an absolute `filename` discarded `export_dir` entirely
  (`Path('/tmp/hw4-exports') / '/tmp/x.txt'` → `/tmp/x.txt`) — both reproduced by the research with
  exit code `0`. Resolving both sides normalises `..` and absolutises the target, and
  `base.resolve() not in target.resolve().parents` is true exactly when the target lies outside the
  directory; it additionally rejects `filename` values of `""` or `"."`, which resolve to the export
  directory itself and are not writable files. Raising before `mkdir`/`write_text` means nothing is
  created on the rejection path, as the criterion requires.
  Returning the unresolved `target` is deliberate and load-bearing: `tests/test_storage.py:62-65`
  asserts `written == tmp_path / "exports" / "report.txt"`, and on macOS `tmp_path` lives under
  `/var/folders/...` while `resolve()` yields `/private/var/folders/...` — returning the resolved
  path would fail that existing test. Verified by prototyping the exact expression: `"report.txt"`
  and `"sub/report.txt"` are accepted, `"../../../../tmp/ESCAPED.txt"`, `"/tmp/absolute-escape.txt"`,
  `"."` and `""` are rejected, and the returned path compares equal to the test's expectation.
- **Verify**: `python3 -m pytest` (expect: 32 passed)

## Execution Order

Apply in this order, running `python3 -m pytest` after each numbered step and requiring
**32 passed** every time. Steps are independent files/functions except where noted.

| Step | Change | Files touched | Test command | Expected |
|---|---|---|---|---|
| 1 | Change 1 — stats zero guard | `src/stats.py` | `python3 -m pytest` | 32 passed |
| 2 | Change 2 (**2a and 2b together**) — priority sort | `src/storage.py` | `python3 -m pytest` | 32 passed |
| 3 | Change 3 — remove fallback token, add `import hmac` | `src/auth.py` | `python3 -m pytest` | 32 passed |
| 4 | Change 4 — constant-time compare, no echo | `src/auth.py` | `python3 -m pytest` | 32 passed |
| 5 | Change 5 — export containment | `src/storage.py` | `python3 -m pytest` | 32 passed |

Ordering notes:

- **2a and 2b must be applied as one step.** Applying 2b alone raises `NameError: PRIORITY_RANK`;
  applying 2a alone is inert but leaves the defect. Run the suite once, after both.
- **Change 3 must precede Change 4.** Change 4's `hmac.compare_digest` call depends on the
  `import hmac` added in Change 3. Applying 4 first would raise `NameError: hmac`.
- Change 5 edits a different function of `src/storage.py` than Change 2 and can be applied at any
  point after step 2; it is listed last so the two `storage.py` edits are verified separately.

Manual smoke checks after step 5 (optional, use `/tmp` scratch paths only — never `data/`):

```bash
cd homework-4
python3 -m src.cli --store /tmp/b1.json add "Anything"
python3 -m src.cli --store /tmp/b1.json stats          # expect: JSON, average_completion_days: 0.0, exit 0

for p in low urgent medium high; do
  python3 -m src.cli --store /tmp/b2.json add "task-$p" --priority "$p"
done
python3 -m src.cli --store /tmp/b2.json list --sort priority   # expect: urgent, high, medium, low

env -u TASKTRACKER_ADMIN_TOKEN python3 -m src.cli --store /tmp/b3.json admin clear --token hw4-admin-secret
# expect: forbidden: admin commands are disabled: TASKTRACKER_ADMIN_TOKEN is not configured, exit 3

python3 -m src.cli --store /tmp/b3.json export "../../../../tmp/ESCAPED.txt" --export-dir /tmp/b-exports
# expect: error: export filename must stay inside the export directory; got '...', exit 2, no file created

rm -f /tmp/b1.json /tmp/b2.json /tmp/b3.json; rm -rf /tmp/b-exports
```

## Risks and Rollback

| Risk | Likelihood | Mitigation |
|---|---|---|
| Change 3 breaks a developer workflow that relied on the built-in `hw4-admin-secret` | Certain — this is the point of the fix | Documented behaviour change: operators must now `export TASKTRACKER_ADMIN_TOKEN=...`. The CLI flag `--token` is unchanged, so no interface breaks. The rejection message names the exact variable to set. |
| `expected_token()` now raises instead of returning, surprising an external caller | Low | The only caller in the repo is `verify_admin_token` → `require_admin` → `src/cli.py:102`, and `AuthError` is already handled there (exit 3). `grep -rn "expected_token\|DEFAULT_ADMIN_TOKEN" src/ tests/` should return only `src/auth.py` matches after the change. |
| Change 5's `resolve()` alters the printed path at `src/cli.py:98` | None | The function returns the **unresolved** `target`; `resolve()` is used only inside the comparison. `tests/test_storage.py:64` guards this. |
| Change 5 rejects a filename a user considers legitimate (e.g. a symlinked export dir) | Low | `resolve()` follows symlinks on both sides consistently, so a symlinked `export_dir` still matches. Subdirectories (`sub/report.txt`) remain allowed. |
| `hmac.compare_digest` raises `TypeError` on exotic token values | None | Both operands are explicitly `.encode("utf-8")`d to `bytes` before the call. |
| Change 2's `PRIORITY_RANK[...]` raises `KeyError` on a hand-edited store file with an unknown priority | None | `TaskStore.load` builds every task through `Task.from_dict` → `Task.__post_init__`, which raises `ValidationError` (exit 2) for an unknown priority long before `list_tasks` runs. |
| A suite regression appears mid-sequence | Low | The per-step `python3 -m pytest` gate localises any regression to the single change just applied. |

**Rollback**: every change is confined to three files — `src/stats.py`, `src/storage.py`,
`src/auth.py`. No test file, no CLI surface, no store-file format, and no `src/cli.py` line is
touched, so reverting is a matter of restoring the "Before" snippet(s) for the offending change and
re-running `python3 -m pytest`. Changes are independent apart from the two stated couplings
(2a↔2b, 3→4), so a single change can be reverted without unwinding the others; reverting Change 3
requires reverting Change 4 as well, since Change 4 depends on its `import hmac`.

## References

Files opened by the planner in this session:

- `context/bugs/BUG-001/bug-context.md` (lines 1-98) — acceptance criteria at 84-91, out of scope at 93-98
- `context/bugs/BUG-001/research/verified-research.md` (lines 1-303) — verdict at 5, discrepancies at 143-180, gate at 222-223
- `src/stats.py` (lines 1-60) — 37-42 (`completion_rate` empty-case convention), **45-49** (fix site), 52-60 (`summarize`)
- `src/storage.py` (lines 1-96) — **9** (fix site 2a), 11-12 (defaults), 14 (`SORT_KEYS`), **65-73** (fix site 2b), 76-84 (`render_report`), **87-96** (fix site 5)
- `src/auth.py` (lines 1-30) — **1-17** (fix site 3), **20-30** (fix site 4)
- `src/cli.py` (lines 1-118) — 32-63 (`build_parser`, flags that must not change), 66-114 (`main`, per corrected reference D-1), 92-99, 101-105, 107-112 (exit-code mapping), 117-118 (entry point)
- `src/models.py` (lines 1-48) — 8-9 (`PRIORITIES`/`STATUSES`), 11-12 (`PRIORITY_RANK`), 31-46 (`__post_init__` validation)
- `tests/test_stats.py` (lines 1-55, per corrected reference D-2) — 42-43, 46-55
- `tests/test_storage.py` (lines 1-65) — 42-53 (sort tests), 62-65 (export equality assertion)
- `tests/test_cli.py` (lines 1-66) — 32-39, 48-55, 58-66 (admin test, `setenv` at 59, `"forbidden:"` at 63)

Read-only command run by the planner (no repository file was modified; it wrote nothing to disk):

```bash
python3 -c '<prototype of the Change 5 containment expression against a temp path>'
# confirmed: "report.txt" and "sub/report.txt" accepted; "../../../../tmp/ESCAPED.txt",
# "/tmp/absolute-escape.txt", "." and "" rejected; the returned unresolved path compares
# equal to tmp_path / "exports" / "report.txt" while resolve() does not (macOS /var vs /private/var)
```
