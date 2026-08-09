# Verified Research — BUG-001

## Verification Summary

**Verdict: PASS** — **Research Quality B (`RELIABLE`)**

| Metric | Value |
|---|---|
| Total checkable claims (`N`) | 76 |
| `VERIFIED` | 73 |
| `DRIFTED` | 2 |
| `WRONG` | 1 |
| `UNVERIFIABLE` | 0 |
| **D1 Reference accuracy** | `(73 + 0.5 × 2) / 76` = `74 / 76` = **97.36%** |
| **D2 Snippet fidelity** | **100%** (6 of 6 quoted snippets match the source character-for-character) |
| **D3 Root-cause coverage** | **`COMPLETE`** |

Every symptom in the bug context (S1, S2, S3a, S3b) is traced to a specific `file:line` cause with an
unambiguous fix location, all six quoted code snippets match the source exactly, and all four
behavioural reproductions were re-run in this session and produced the output the research reported.
The single `WRONG` claim is a descriptive line-count statistic in the codebase map that no fix
depends on. **The Bug Planner may proceed**, using the corrected references in *Discrepancies Found*
in place of the original claims.

## Verified Claims

### Codebase Map

| # | Claim | Cited location | Verdict | Evidence |
|---|---|---|---|---|
| 1 | `src/__init__.py` is 3 lines; `__version__ = "1.0.0"` on line 3 | `src/__init__.py:3` | `VERIFIED` | Opened file: 3 lines; line 3 is `__version__ = "1.0.0"`. `wc -l` → 3 |
| 2 | `src/models.py` is 77 lines | `src/models.py` | `VERIFIED` | `wc -l src/models.py` → 77 |
| 3 | `Task.__post_init__` spans 31-46 | `src/models.py:31-46` | `VERIFIED` | Line 31 `def __post_init__`, line 46 `self.completed_at = date.today().isoformat()` |
| 4 | `Task.to_dict`/`from_dict` span 48-77 | `src/models.py:48-77` | `VERIFIED` | Line 48 `def to_dict`, line 60 `@classmethod`, line 61 `def from_dict`, file ends line 77 |
| 5 | `PRIORITIES`/`STATUSES` tuples | `src/models.py:8-9` | `VERIFIED` | Line 8 `PRIORITIES = ("urgent", "high", "medium", "low")`, line 9 `STATUSES = (...)` |
| 6 | `PRIORITY_RANK` severity map | `src/models.py:12` | `VERIFIED` | Line 12 `PRIORITY_RANK = {name: index for index, name in enumerate(PRIORITIES)}` |
| 7 | `src/stats.py` is 60 lines | `src/stats.py` | `VERIFIED` | `wc -l src/stats.py` → 60 |
| 8 | `completion_days` spans 14-18 | `src/stats.py:14-18` | `VERIFIED` | Line 14 `def completion_days`, line 18 the `return (_parse(...)).days` |
| 9 | `completion_rate` spans 37-42 | `src/stats.py:37-42` | `VERIFIED` | Line 37 `def completion_rate`, line 42 `return round(done * 100 / len(tasks), 1)` |
| 10 | `average_completion_days` spans 45-49 | `src/stats.py:45-49` | `VERIFIED` | Line 45 `def average_completion_days`, line 49 `return round(total_days / len(completed), 2)` |
| 11 | `summarize` spans 52-60 | `src/stats.py:52-60` | `VERIFIED` | Line 52 `def summarize`, dict closes on line 60 |
| 12 | `src/storage.py` is 96 lines | `src/storage.py` | `VERIFIED` | `wc -l src/storage.py` → 96 |
| 13 | `TaskStore.load/save/add/complete/clear` span 23-62 | `src/storage.py:23-62` | `VERIFIED` | Line 23 `def load`, line 62 `return len(tasks)` (end of `clear`) |
| 14 | `list_tasks` spans 65-73 | `src/storage.py:65-73` | `VERIFIED` | Line 65 `def list_tasks`, line 73 the `created` fallback `return sorted(...)` |
| 15 | `render_report` spans 76-84 | `src/storage.py:76-84` | `VERIFIED` | Line 76 `def render_report`, line 84 `return "\n".join(lines) + "\n"` |
| 16 | `export_report` spans 87-96 | `src/storage.py:87-96` | `VERIFIED` | Line 87 `def export_report(`, line 96 `return target` |
| 17 | `src/auth.py` is 30 lines; `expected_token` 15-17, `verify_admin_token` 20-24, `require_admin` 27-30 | `src/auth.py:15-17,20-24,27-30` | `VERIFIED` | `wc -l` → 30; all three `def` lines and their final statements land exactly as cited |
| 18 | `src/cli.py` is 118 lines; `build_parser` spans 32-63 | `src/cli.py:32-63` | `VERIFIED` | `wc -l src/cli.py` → 118; line 32 `def build_parser`, line 63 `return parser` |
| 19 | `main` spans `cli.py:66-118` | `src/cli.py:66-118` | `DRIFTED` | Line 66 `def main` is exact, but the function body ends at line 114 (`return 1`); lines 117-118 are the module `__main__` guard. See D-1 |
| 20 | `tests/` is "668 total lines across all files" | `tests/` | `WRONG` | `wc -l tests/*.py` → 48+66+50+55+65 = **284**. 668 is the combined `src/*.py` + `tests/*.py` total. See D-3 |
| 21 | pytest suite has 32 tests | `tests/` | `VERIFIED` | Ran `python3 -m pytest` → `32 passed in 0.07s` |
| 22 | `tests/conftest.py` provides `store`, `store_path`, `sample_tasks` | `tests/conftest.py:16-48` | `VERIFIED` | `store_path` line 17, `store` line 23, `sample_tasks` line 29 |
| 23 | One `test_*.py` per source module except `auth.py`; no `tests/test_auth.py` exists | `tests/` | `VERIFIED` | `find src tests -name "*.py"` lists only `test_cli/test_models/test_stats/test_storage.py`; no `test_auth.py`. (`src/__init__.py`, a 1-line version marker, also has none — immaterial) |

### F1 — `stats` crashes with no completed tasks

| # | Claim | Cited location | Verdict | Evidence |
|---|---|---|---|---|
| 24 | `average_completion_days` divides `total_days` by `len(completed)` with no zero guard | `src/stats.py:47-49` | `VERIFIED` | Read: lines 47-49 build `completed`, sum, then divide — no `if not completed` branch |
| 25 | `completion_rate`, directly above, already special-cases the empty collection with an early return | `src/stats.py:39-40` | `VERIFIED` | Lines 39-40: `if not tasks: return 0.0` |
| 26 | Fault location is `src/stats.py:49`; function defined at `src/stats.py:45` | `src/stats.py:45,49` | `VERIFIED` | Both lines land exactly as cited |
| 27 | Snippet of `src/stats.py:37-49` presented verbatim | `src/stats.py:37-49` | `VERIFIED` | **Snippet claim** — matches source character-for-character, including the two blank separator lines |
| 28 | Crash is triggered from `src/cli.py:93`: `print(json.dumps(summarize(store.load()), indent=2))` | `src/cli.py:93` | `VERIFIED` | Line 93 matches verbatim; runtime traceback names `cli.py, line 93, in main` |
| 29 | `summarize` calls `average_completion_days` at `src/stats.py:59` | `src/stats.py:59` | `VERIFIED` | Line 59 `"average_completion_days": average_completion_days(tasks),`; traceback frame confirms |
| 30 | Reproduction yields `ZeroDivisionError: division by zero` through frames cli.py:93 → stats.py:59 → stats.py:49 | repro command | `VERIFIED` | **Ran** `python3 -m src.cli --store /tmp/v1.json add "Anything"` then `... stats` under `/tmp`; traceback frames matched line-for-line |
| 31 | Observed exit code is `1` (unhandled-exception fallthrough) | repro command | `VERIFIED` | **Ran**: `EXIT=1` |
| 32 | `src/cli.py:107-112` catches only `ValidationError`/`KeyError` (→2) and `AuthError` (→3), so `ZeroDivisionError` is unhandled | `src/cli.py:107-112` | `VERIFIED` | Lines 107-112 read exactly that; no bare `except` |
| 33 | `test_average_completion_days_over_completed_tasks` only calls it on `sample_tasks` | `tests/test_stats.py:42-43` | `VERIFIED` | Lines 42-43 are exactly that test, single assertion `== 4.0` |
| 34 | `sample_tasks` always contains one `done` task | `tests/conftest.py:32-39` | `VERIFIED` | Lines 32-39 build `Task(id=1, ..., status="done", completed_at="2026-01-05")` |
| 35 | `test_complete_and_stats` always completes a task before `stats`; no test exercises zero completed tasks or an empty list | `tests/test_cli.py:32-39` | `VERIFIED` | Lines 32-39: `complete 1` precedes `stats`. Read all four test files — no call to `stats`/`summarize`/`average_completion_days` with zero completed tasks |

### F2 — `list --sort priority` wrong order

| # | Claim | Cited location | Verdict | Evidence |
|---|---|---|---|---|
| 36 | The `"priority"` branch sorts by the raw string `task.priority` | `src/storage.py:69-70` | `VERIFIED` | Line 69 `if sort == "priority":`, line 70 `return sorted(tasks, key=lambda task: task.priority)` |
| 37 | Alphabetically `"high" < "low" < "medium" < "urgent"` | behavioural | `VERIFIED` | **Ran** the repro; output order was high, low, medium, urgent |
| 38 | `PRIORITY_RANK` is built from `PRIORITIES = ("urgent", "high", "medium", "low")` with index 0 = most severe | `src/models.py:8,12` | `VERIFIED` | Lines 8 and 12 confirm; comment on line 11 states "0 = most severe" |
| 39 | `storage.py` never imports or uses `PRIORITY_RANK` | `src/storage.py:9` | `VERIFIED` | Line 9 imports only `Task, ValidationError`; `grep -rn "PRIORITY_RANK" src/` matches only `src/models.py:12` |
| 40 | Fault at `src/storage.py:69-70`; `list_tasks` defined at `src/storage.py:65`; severity map at `src/models.py:8-12` | as cited | `VERIFIED` | All three land exactly |
| 41 | Snippet of `src/storage.py:65-73` presented verbatim | `src/storage.py:65-73` | `VERIFIED` | **Snippet claim** — exact match |
| 42 | Snippet of `src/models.py:8-12` presented verbatim | `src/models.py:8-12` | `VERIFIED` | **Snippet claim** — exact match, including the `#:` comment line |
| 43 | Repro output is `high, low, medium, urgent` | repro command | `VERIFIED` | **Ran** the four `add` commands against `/tmp/v2.json` then `list --sort priority`; output identical to the research listing |
| 44 | `tests/test_storage.py` covers `sort="created"` (42-43), `sort="title"` (46-48) and the invalid key (51-53), but has no `sort="priority"` test | `tests/test_storage.py:42-53` | `VERIFIED` | All three tests land on the cited lines; read the whole 65-line file — no priority-sort test exists |
| 45 | `test_priority_rank_orders_by_severity` only asserts on `PRIORITY_RANK` itself, not on `list_tasks` | `tests/test_models.py:49-50` | `VERIFIED` | Line 50 asserts `PRIORITY_RANK["urgent"] < ... < PRIORITY_RANK["medium"]` only |
| 46 | `sorted()` is stable; the `"priority"` branch has no secondary key while the `"created"` branch uses `(task.created_at, task.id)` | `src/storage.py:70,73` | `VERIFIED` | Line 70 single-key lambda; line 73 tuple key. Correctly labelled by the research as a design gap, not a reproduced defect |

### F3a — Hardcoded fallback admin token

| # | Claim | Cited location | Verdict | Evidence |
|---|---|---|---|---|
| 47 | `expected_token()` falls back to `DEFAULT_ADMIN_TOKEN = "hw4-admin-secret"` when `TASKTRACKER_ADMIN_TOKEN` is unset | `src/auth.py:8,17` | `VERIFIED` | Line 8 defines the constant; line 17 `return os.environ.get(ENV_VAR, DEFAULT_ADMIN_TOKEN)` |
| 48 | Locations: constant `auth.py:8`; `expected_token` `auth.py:15-17`; `require_admin` `auth.py:27-30`; called from `cli.py:102` | as cited | `VERIFIED` | All land exactly; `cli.py:102` is `require_admin(args.token)` |
| 49 | Snippet of `src/auth.py:1-17` presented verbatim | `src/auth.py:1-17` | `VERIFIED` | **Snippet claim** — exact match including docstrings and blank lines |
| 50 | With the env var unset, `expected_token()` returns `'hw4-admin-secret'` and `require_admin('hw4-admin-secret')` does not raise | behavioural | `VERIFIED` | **Ran** with `os.environ.pop('TASKTRACKER_ADMIN_TOKEN', None)`: printed `expected_token: 'hw4-admin-secret'` and `require_admin(default) did NOT raise` |
| 51 | `src/cli.py:101-105` would then proceed to `store.clear()` | `src/cli.py:101-105` | `VERIFIED` | Lines 101-105: `require_admin` → `store.clear()` → print → `return 0`; nothing else gates it |
| 52 | `test_admin_clear_requires_token` sets `monkeypatch.setenv("TASKTRACKER_ADMIN_TOKEN", "s3cret-for-test")`, so it never observes the fallback | `tests/test_cli.py:58-66` | `VERIFIED` | Line 59 is the `setenv`; the test spans 58-66 |

### F3b — Non-constant-time comparison and token echo

| # | Claim | Cited location | Verdict | Evidence |
|---|---|---|---|---|
| 53 | `verify_admin_token` compares with plain `==`, which is not constant-time | `src/auth.py:24` | `VERIFIED` | Line 24 `return provided == expected_token()` (verified by code inspection, as the research states) |
| 54 | Comparison at `auth.py:24` inside `verify_admin_token` (`auth.py:20-24`); message built at `auth.py:30` inside `require_admin` (`auth.py:27-30`) | as cited | `VERIFIED` | All four line references land exactly |
| 55 | `require_admin` builds its `AuthError` with `{provided!r}`, echoing the caller's guess | `src/auth.py:30` | `VERIFIED` | Line 30 `raise AuthError(f"admin token rejected: {provided!r}")` |
| 56 | `src/cli.py:110-112` prints it to stderr as `forbidden: admin token rejected: '<guess>'` | `src/cli.py:110-112` | `VERIFIED` | **Ran** `python3 -m src.cli --store /tmp/v3.json admin clear --token "wrong-guess"` → stderr `forbidden: admin token rejected: 'wrong-guess'`, `EXIT=3` |
| 57 | Snippet of `src/auth.py:20-30` presented verbatim | `src/auth.py:20-30` | `VERIFIED` | **Snippet claim** — exact match |
| 58 | No constant-time primitive (`hmac`/`compare_digest`) is imported or used anywhere in `src/` | `src/` | `VERIFIED` | **Ran** `grep -rn "hmac\|compare_digest" src/ tests/` → no matches |
| 59 | `tests/test_cli.py` only asserts the substring `"forbidden:"` in stderr (line 63); nothing asserts timing safety or non-echo | `tests/test_cli.py:63` | `VERIFIED` | Line 63 `assert "forbidden:" in err`; no other admin assertion exists in the suite |

### F4 — `export` path traversal

| # | Claim | Cited location | Verdict | Evidence |
|---|---|---|---|---|
| 60 | `export_report` builds the target as `Path(export_dir) / filename` with no containment check | `src/storage.py:93` | `VERIFIED` | Line 93 `target = Path(export_dir) / filename`; lines 94-96 mkdir/write/return, no validation. `grep -rn "resolve\|commonpath\|is_relative_to" src/` → no matches |
| 61 | Fault at `src/storage.py:93`; function defined `src/storage.py:87-96` | as cited | `VERIFIED` | Both land exactly |
| 62 | Snippet of `src/storage.py:87-96` presented verbatim | `src/storage.py:87-96` | `VERIFIED` | **Snippet claim** — exact match including the multi-line signature |
| 63 | `..`-traversal repro writes outside the export dir, prints the unnormalised path, exit code `0` | repro command | `VERIFIED` | **Ran** `export "../../../../tmp/VERIFY-ESCAPED.txt" --export-dir /tmp/hw4v-exports` → `report written to /tmp/hw4v-exports/../../../../tmp/VERIFY-ESCAPED.txt`, `EXIT=0`, and `/tmp/VERIFY-ESCAPED.txt` existed (24 bytes). Cleaned up afterwards |
| 64 | `Path('/tmp/hw4-exports') / '/tmp/absolute-escape.txt'` yields `/tmp/absolute-escape.txt`, i.e. an absolute `filename` discards `export_dir` | behavioural | `VERIFIED` | **Ran** the same one-liner → `/tmp/absolute-escape.txt` |
| 65 | Both export tests pass only the safe filename `"report.txt"` | `tests/test_storage.py:62-65`, `tests/test_cli.py:48-55` | `VERIFIED` | Both tests land on the cited lines and both use `"report.txt"` |
| 66 | No test asserts rejection of `..` segments or absolute paths | `tests/` | `VERIFIED` | Read all four test files; no such assertion exists |

### Related Code Worth Knowing / References

| # | Claim | Cited location | Verdict | Evidence |
|---|---|---|---|---|
| 67 | `PRIORITY_RANK = {name: index for index, name in enumerate(PRIORITIES)}` is the ready-made severity map | `src/models.py:12` | `VERIFIED` | Line 12 matches verbatim |
| 68 | `sorted(tasks, key=lambda task: (task.created_at, task.id))` is the existing tie-break convention | `src/storage.py:73` | `VERIFIED` | Line 73 matches verbatim |
| 69 | Exit-code convention: `ValidationError`/`KeyError` → 2, `AuthError` → 3, unhandled → Python default (1) | `src/cli.py:107-112` | `VERIFIED` | Lines 107-112; both exit codes confirmed at runtime (`EXIT=3` for auth, `EXIT=1` for the `ZeroDivisionError`) |
| 70 | `ENV_VAR = "TASKTRACKER_ADMIN_TOKEN"` and `DEFAULT_ADMIN_TOKEN` are the two names an F3a fix must touch | `src/auth.py:7-8` | `VERIFIED` | Lines 7-8 match verbatim |
| 71 | `DEFAULT_STORE_PATH = Path("data/tasks.json")`, `DEFAULT_EXPORT_DIR = Path("exports")` | `src/storage.py:11-12` | `VERIFIED` | Lines 11-12 match verbatim |
| 72 | `src/auth.py` has zero direct unit-test coverage; every admin assertion goes through the full CLI | `tests/` | `VERIFIED` | No `test_auth.py`; the only admin assertions are `tests/test_cli.py:58-66` |
| 73 | `context/bugs/BUG-001/bug-context.md` is 98 lines | `context/bugs/BUG-001/bug-context.md:1-98` | `VERIFIED` | Opened the full file; last line 98 is `- Changing the JSON store file format.` |
| 74 | Reference list: `tests/test_stats.py` (lines 1-56) | `tests/test_stats.py:1-56` | `DRIFTED` | The file is **55** lines (`wc -l` → 55); line 55 is the closing `}` of `test_summarize_reports_every_section`. See D-2 |
| 75 | Remaining reference ranges: `src/__init__.py` 1-3, `src/auth.py` 1-30, `src/cli.py` 1-118, `src/models.py` 1-77, `src/stats.py` 1-60, `src/storage.py` 1-96, `tests/conftest.py` 1-48, `tests/test_cli.py` 1-66, `tests/test_models.py` 1-50, `tests/test_storage.py` 1-65 | as cited | `VERIFIED` | `wc -l` on all ten files returned exactly these counts |
| 76 | `python3 -m pytest -q` → 32 passed | test command | `VERIFIED` | **Ran** `python3 -m pytest` → `32 passed in 0.07s` |

*Not scored (explicit non-claims):* the research's own confidence caveat that the F3b timing side
channel's **practical exploitability** was never measured, and the three entries under *Open
Questions*, are self-declared limitations and design questions rather than assertions about the
repository.

## Discrepancies Found

### D-1 — `main` line range overshoots the function body (claim #19, `DRIFTED`)

- **What the research said:** `` `main` (cli.py:66-118) `` in the Codebase Map row for `src/cli.py`.
- **What the source actually says:** `def main(argv: list[str] | None = None) -> int:` is on line 66
  (exact), but the function body ends at line 114 with `return 1`. Line 115 is blank, line 117 is
  `if __name__ == "__main__":  # pragma: no cover - process entry point`, and line 118 is
  `raise SystemExit(main())` — module level, not part of `main`.
- **Corrected reference:** **`src/cli.py:66-114`** is `main`; **`src/cli.py:117-118`** is the process
  entry point.
- **Impact on the fix:** None. The entry point on line 66 is correct, and every fine-grained
  reference the plan depends on inside `main` (`cli.py:93`, `cli.py:96-99`, `cli.py:101-105`,
  `cli.py:107-112`) was independently verified as exact.

### D-2 — `tests/test_stats.py` reference range off by one (claim #74, `DRIFTED`)

- **What the research said:** References section lists `tests/test_stats.py` (lines 1-56).
- **What the source actually says:** the file is 55 lines; line 55 is the closing `}` of the
  `set(summary)` assertion in `test_summarize_reports_every_section`. Line 56 does not exist.
- **Corrected reference:** **`tests/test_stats.py:1-55`**.
- **Impact on the fix:** None. The one line reference the plan uses from this file,
  `tests/test_stats.py:42-43` (`test_average_completion_days_over_completed_tasks`), is exact.

### D-3 — `tests/` line-count is wrong (claim #20, `WRONG`)

- **What the research said:** Codebase Map row: `` tests/ (668 total lines across all files) ``.
- **What the source actually says:** `wc -l tests/*.py` → `conftest.py` 48 + `test_cli.py` 66 +
  `test_models.py` 50 + `test_stats.py` 55 + `test_storage.py` 65 = **284 lines**. The figure 668 is
  the combined `src/*.py` **plus** `tests/*.py` total, i.e. the `total` row of
  `wc -l src/*.py tests/*.py` was transcribed into a tests-only cell.
- **Corrected reference:** **`tests/` is 284 lines across 5 files** (`tests/conftest.py` 48,
  `tests/test_cli.py` 66, `tests/test_models.py` 50, `tests/test_stats.py` 55,
  `tests/test_storage.py` 65). The 668 figure is `src/` (384) + `tests/` (284).
- **Impact on the fix:** None. This is a descriptive size statistic; no fix location, symptom, or
  root cause depends on it. Every per-file line count in the same table (`src/*.py`,
  and each individual test file in the References section) was verified correct. Notably the adjacent
  claim in the same cell — "32 tests total" — is correct.

## Research Quality Assessment

**Computed level: B (`RELIABLE`) — `PASS`.**

**Arithmetic**

- `N` = 76 checkable claims (23 codebase-map, 12 F1, 11 F2, 6 F3a, 7 F3b, 7 F4, 6 related-code,
  4 reference/test-command).
- `VERIFIED` = 73, `DRIFTED` = 2 (#19, #74), `WRONG` = 1 (#20), `UNVERIFIABLE` = 0.
- **D1** = `(VERIFIED + 0.5 × DRIFTED) / N` = `(73 + 0.5 × 2) / 76` = `74 / 76` = `0.973684…` →
  **97.36%** (truncated, never rounded up across a threshold — this is *not* 98%).
- **D2** = 6 snippet claims (#27 `stats.py:37-49`, #41 `storage.py:65-73`, #42 `models.py:8-12`,
  #49 `auth.py:1-17`, #57 `auth.py:20-30`, #62 `storage.py:87-96`); all 6 match the source
  character-for-character → `6 / 6` = **100%**.
- **D3** = **`COMPLETE`**. Reasoning: all four reported symptoms are traced to a specific `file:line`
  cause with an unambiguous fix site — S1 → `src/stats.py:49`, S2 → `src/storage.py:69-70`,
  S3a → `src/auth.py:8` + `src/auth.py:17`, S3b → `src/auth.py:24` and `src/auth.py:30`, and the
  export escape → `src/storage.py:93` — and each was reproduced end-to-end in this session.

**Level selection (scanning from A down)**

- **A (`VERIFIED`)** — fails twice: D1 97.36% < 98%, and there is one `WRONG` claim (A requires zero).
- **B (`RELIABLE`)** — every condition met: D1 97.36% ≥ 90% ✓; D2 100% ≥ 90% ✓; D3 `COMPLETE` ✓;
  hard blocker "zero `WRONG` on a claim the plan depends on" ✓ — the only `WRONG` claim (D-3) is the
  `tests/` aggregate line count, which names no fix site and is contradicted by no other claim in the
  document. **Level B.**

**Escalation rules applied**

- *"Any `WRONG` claim about a file that the fix must touch caps the level at C."* — **Does not fire.**
  Claim #20 is not about a file: it is an aggregate line-count for the `tests/` directory. Every
  individual file the fix must touch (`src/stats.py`, `src/storage.py`, `src/auth.py`, `src/cli.py`)
  and every individual test file in the References list carries a *correct* line count and correct
  line references. No planner reading this report could be misdirected by the corrected statistic.
- *"A missing file caps the level at C."* — **Does not fire.** Every cited path exists; the absence
  of `tests/test_auth.py` is asserted *as an absence* by the research and is itself correct.
- *"`D3 = MISSING` caps at E."* — **Does not fire.** D3 is `COMPLETE`.
- *"Never round a percentage up across a threshold."* — Applied: 97.36% was **not** promoted to 98%,
  which is what keeps this at B rather than A.

**Gate decision:** Level B is a `PASS`. The Bug Planner may proceed, substituting the three corrected
references in *Discrepancies Found* for the original claims.

**What would have to change to reach A**

Correct all three discrepancies — restate the `tests/` size as 284 lines (D-3), narrow `main` to
`src/cli.py:66-114` (D-1), and fix the `tests/test_stats.py` reference to lines 1-55 (D-2). That
would give `VERIFIED` = 76, `DRIFTED` = 0, `WRONG` = 0, hence D1 = `76/76` = 100% ≥ 98% with D2 100%
and D3 `COMPLETE`, satisfying every level-A condition including the zero-`WRONG`/zero-`UNVERIFIABLE`
blockers.

**Verifier's note on research strengths (not scored):** all six code snippets are byte-exact, all
four reproductions replayed identically in this session under `/tmp`, and the document correctly
distinguishes reproduced defects from design gaps (the priority tie-break note under F2) and from
unmeasured claims (the F3b timing-exploitability caveat). The residual defects are transcription
slips in descriptive metadata, not in any fix-bearing reference.

## References

Files opened in this session:

- `context/bugs/BUG-001/bug-context.md` (lines 1-98)
- `context/bugs/BUG-001/research/codebase-research.md` (lines 1-409)
- `src/__init__.py` (lines 1-3) — line 3
- `src/models.py` (lines 1-77) — lines 8, 9, 11, 12, 31-46, 48-58, 60-77
- `src/stats.py` (lines 1-60) — lines 14-18, 37-42, 45-49, 52-60
- `src/storage.py` (lines 1-96) — lines 9, 11-12, 14, 23-62, 65-73, 76-84, 87-96
- `src/auth.py` (lines 1-30) — lines 7, 8, 15-17, 20-24, 27-30
- `src/cli.py` (lines 1-118) — lines 32-63, 66, 92-99, 101-105, 107-112, 114, 117-118
- `tests/conftest.py` (lines 1-48) — lines 16-19, 22-25, 28-48, 32-39
- `tests/test_cli.py` (lines 1-66) — lines 32-39, 42-45, 48-55, 58-66, 63
- `tests/test_models.py` (lines 1-50) — lines 43-46, 49-50
- `tests/test_stats.py` (lines 1-55) — lines 29-30, 42-43, 46-55
- `tests/test_storage.py` (lines 1-65) — lines 42-43, 46-48, 51-53, 62-65
- `pytest.ini` (lines 1-4)

Commands run during verification (read-only, or writing only to `/tmp` scratch paths that were
deleted afterwards; `data/` was never touched and no source or test file was modified):

```bash
wc -l src/*.py tests/*.py
find src tests -type f -name "*.py" | sort
cat pytest.ini
python3 -m pytest                       # -> 32 passed in 0.07s

rm -f /tmp/v1.json
python3 -m src.cli --store /tmp/v1.json add "Anything"
python3 -m src.cli --store /tmp/v1.json stats   # -> ZeroDivisionError, EXIT=1

rm -f /tmp/v2.json
for p in low urgent medium high; do
  python3 -m src.cli --store /tmp/v2.json add "task-$p" --priority "$p"
done
python3 -m src.cli --store /tmp/v2.json list --sort priority   # -> high, low, medium, urgent

python3 -c "
import os
os.environ.pop('TASKTRACKER_ADMIN_TOKEN', None)
from src.auth import expected_token, require_admin, AuthError
print('expected_token:', repr(expected_token()))
require_admin('hw4-admin-secret')
try:
    require_admin('wrong-guess')
except AuthError as e:
    print('AuthError:', e)
"

python3 -m src.cli --store /tmp/v3.json admin clear --token "wrong-guess"   # -> EXIT=3

mkdir -p /tmp/hw4v-exports
python3 -m src.cli --store /tmp/v3.json export "../../../../tmp/VERIFY-ESCAPED.txt" \
  --export-dir /tmp/hw4v-exports        # -> EXIT=0, /tmp/VERIFY-ESCAPED.txt created
ls -l /tmp/VERIFY-ESCAPED.txt
python3 -c "from pathlib import Path; print(Path('/tmp/hw4v-exports') / '/tmp/absolute-escape.txt')"

grep -rn "hmac\|compare_digest" src/ tests/          # -> no matches
grep -rn "resolve\|commonpath\|is_relative_to" src/  # -> no matches
grep -rn "PRIORITY_RANK" src/ tests/                 # -> src/models.py:12, tests/test_models.py:7,50

rm -f /tmp/v1.json /tmp/v2.json /tmp/v3.json /tmp/VERIFY-ESCAPED.txt
rm -rf /tmp/hw4v-exports
```
