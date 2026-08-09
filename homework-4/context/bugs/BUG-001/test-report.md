# Test Report — BUG-001

## Scope

Tests target only the functions listed in `fix-summary.md`'s **Changed Files** table:

- `src/stats.py::average_completion_days` (defect S1)
- `src/storage.py::list_tasks` (defect S2) and `src/storage.py::export_report` (defect S3.2/F4)
- `src/auth.py::expected_token`, `verify_admin_token`, `require_admin` (defects S3a, S3b)

Deliberately **not** tested:

- `src/cli.py` — untouched by the fix (per `fix-summary.md`'s Deviations section); the existing
  `tests/test_cli.py::test_admin_clear_requires_token` and `test_export_writes_file` already cover
  the CLI surface end-to-end and were left alone.
- `src/models.py` — untouched; `PRIORITY_RANK` is exercised indirectly through `list_tasks`.
- `count_by_status`, `count_by_priority`, `completion_rate`, `completion_days`, `render_report`,
  `TaskStore.add/complete/clear/load/save` — untouched by the fix and already covered by the
  baseline suite (`tests/test_stats.py`, `tests/test_storage.py`).
- Literal timing/side-channel proof that `hmac.compare_digest` is constant-time — not observable
  from a fast, deterministic unit test; see Coverage Gaps.

## Generated Tests

| Test file | Test name | Defect | Kind | What it pins | Pre-fix verdict |
|---|---|---|---|---|---|
| `tests/test_stats_fixes.py` | `test_average_completion_days_with_no_completed_tasks_returns_zero` | S1 | regression | `average_completion_days` returns `0.0` for a non-empty task list with zero completed tasks | **Would have failed**: pre-fix code computed `total_days / len(completed)` unconditionally; `len(completed) == 0` raised `ZeroDivisionError` instead of returning, per the "Before" snippet in `fix-summary.md`. |
| `tests/test_stats_fixes.py` | `test_average_completion_days_of_empty_collection_is_zero` | S1 | boundary | the empty-collection edge (`tasks == []`) the crash lived on | **Would have failed**: same `ZeroDivisionError` path as above, at the most extreme boundary (no tasks at all). |
| `tests/test_stats_fixes.py` | `test_average_completion_days_averages_across_multiple_completed_tasks` | S1 | neighbour | the mean computation over 2 completed tasks with different day-spans is unaffected by the new guard | **Would have passed** pre-fix too: `completed` is non-empty, so the division executes normally in both versions; confirmed by re-reading the "Before" snippet — the added code is only the `if not completed: return 0.0` branch, which this input never enters. |
| `tests/test_storage_fixes.py` | `test_sort_by_priority_orders_by_severity_not_alphabetically` | S2 | regression | `list_tasks(sort="priority")` orders by `PRIORITY_RANK` (urgent, high, medium, low), not alphabetically | **Would have failed**: pre-fix `key=lambda task: task.priority` sorts the strings alphabetically (`"high" < "low" < "medium" < "urgent"`), giving ids `[4, 1, 3, 2]` instead of the expected `[2, 4, 3, 1]`. |
| `tests/test_storage_fixes.py` | `test_sort_by_priority_breaks_ties_by_created_at_then_id` | S2 | boundary | two tasks tied on priority *and* `created_at` are ordered deterministically by `id` | **Would have failed**: pre-fix `key=lambda task: task.priority` treats both tasks as equal, so Python's stable sort keeps the original list order `[5, 2]`; the fix's compound key `(rank, created_at, id)` produces `[2, 5]`. |
| `tests/test_storage_fixes.py` | `test_sort_by_title_still_case_insensitive_after_priority_fix` | S2 | neighbour | the untouched `sort="title"` branch still works after the edit | **Would have passed** pre-fix too: the `title` branch of `list_tasks` was not touched by the diff (only the `priority` branch and the module import changed). |
| `tests/test_storage_fixes.py` | `test_export_rejects_dot_dot_traversal_and_writes_nothing` | S3.2/F4 | regression | `export_report` raises `ValidationError` for a `../escape.txt` filename and writes nothing outside `export_dir` | **Would have failed**: the "Before" snippet has no containment check at all — it joins `export_dir / filename` and writes unconditionally, so no `ValidationError` would be raised and `escape.txt` would land in `tmp_path` (matching the bug report's manual repro). |
| `tests/test_storage_fixes.py` | `test_export_rejects_absolute_path_escape` | S3.2/F4 | boundary | an absolute filename (which `Path.__truediv__` uses verbatim, discarding `export_dir`) is rejected | **Would have failed**: same reasoning — pre-fix, `Path(export_dir) / "/abs/path"` evaluates to the absolute path, and the function writes there with no check. |
| `tests/test_storage_fixes.py` | `test_export_still_writes_legitimate_nested_filename` | S3.2/F4 | neighbour | a nested-but-contained filename (`sub/dir/report.txt`) still succeeds after the guard was added | **Would have passed** pre-fix too: the target is genuinely inside `export_dir`, so both versions write successfully — confirms the fix does not break legitimate nested exports. |
| `tests/test_auth_fixes.py` | `test_expected_token_raises_when_env_var_unset` | S3a | regression | `expected_token()` raises `AuthError` when `TASKTRACKER_ADMIN_TOKEN` is unset | **Would have failed**: pre-fix `os.environ.get(ENV_VAR, DEFAULT_ADMIN_TOKEN)` returns the hardcoded `"hw4-admin-secret"` instead of raising. |
| `tests/test_auth_fixes.py` | `test_expected_token_raises_when_env_var_is_empty_string` | S3a | boundary | an empty-string env value is treated as "not configured", not as a valid empty token | **Would have failed**: pre-fix `.get(ENV_VAR, DEFAULT)` returns `""` because the key *is* present (even though empty), never touching the default, so no exception is raised and `""` would silently be treated as the expected token. |
| `tests/test_auth_fixes.py` | `test_expected_token_returns_configured_value` | S3a | neighbour | a properly configured token is still returned unchanged | **Would have passed** pre-fix too: `.get(ENV_VAR, DEFAULT)` returns the configured value in both versions when the var is set to a non-empty string. |
| `tests/test_auth_fixes.py` | `test_require_admin_rejection_message_does_not_echo_supplied_token` | S3b | regression | `require_admin` raises `AuthError` with the exact message `"admin token rejected"`, never echoing the caller-supplied value | **Would have failed**: pre-fix message is `f"admin token rejected: {provided!r}"`, so both the exact-string equality and the `not in` check would fail — `str(excinfo.value)` would be `"admin token rejected: 'attacker-supplied-secret'"`, which contains the supplied token. |
| `tests/test_auth_fixes.py` | `test_verify_admin_token_with_none_raises_when_no_token_configured` | S3b | boundary | with no token configured, `verify_admin_token(None)` now raises `AuthError` instead of silently returning `False` | **Would have failed**: pre-fix short-circuits on `if provided is None: return False` *before* calling `expected_token()`, so an unconfigured install returns `False` with no exception; post-fix calls `expected_token()` unconditionally first, surfacing the missing configuration even for `None` input. |
| `tests/test_auth_fixes.py` | `test_verify_admin_token_returns_false_for_none_when_token_is_configured` | S3b | neighbour | with a token configured, `verify_admin_token(None)` still returns `False` | **Would have passed** pre-fix too: `expected_token()` succeeds in both versions when a token is configured, so the final result (`False` for `None`) is unchanged by the reordering. |
| `tests/test_auth_fixes.py` | `test_verify_admin_token_returns_true_for_matching_token` | S3b | neighbour | the switch to `hmac.compare_digest` still accepts the correct token | **Would have passed** pre-fix too: `provided == expected_token()` and `hmac.compare_digest(...)` agree on equal byte strings. |
| `tests/test_auth_fixes.py` | `test_verify_admin_token_returns_false_for_wrong_token` | S3b | neighbour | the switch to `hmac.compare_digest` still rejects a wrong token | **Would have passed** pre-fix too: `==` and `hmac.compare_digest` agree on unequal byte strings. |

Defect coverage check against `fix-summary.md`'s Changed Files table: S1 ✅ (3 tests), S2 ✅ (3
tests), S3.2/F4 ✅ (3 tests), S3a ✅ (3 tests), S3b ✅ (5 tests). Every defect has at least one
regression, one boundary and one neighbour test.

## Test Execution

**Full suite before adding new tests** (baseline, as reported in `fix-summary.md` and reproduced
here):

```
$ python3 -m pytest
................................                                         [100%]
32 passed in 0.30s
```

**Full suite after adding the new test files:**

```
$ python3 -m pytest -v
tests/test_auth_fixes.py ........                                        [ 16%]
tests/test_cli.py ......                                                 [ 28%]
tests/test_models.py ........                                            [ 44%]
tests/test_stats.py ........                                             [ 61%]
tests/test_stats_fixes.py ...                                            [ 67%]
tests/test_storage.py ..........                                         [ 87%]
tests/test_storage_fixes.py ......                                       [100%]

============================== 49 passed in 0.11s ==============================
```

49 = 32 baseline + 8 (`test_auth_fixes.py`) + 3 (`test_stats_fixes.py`) + 6 (`test_storage_fixes.py`)
new tests. No existing test file was modified.

**One generated file run in isolation** (demonstrates independence — no shared state, no ordering
dependency on the rest of the suite):

```
$ python3 -m pytest tests/test_auth_fixes.py -v
collected 8 items

tests/test_auth_fixes.py ........                                        [100%]

============================== 8 passed in 0.02s ===============================
```

All three new files were also spot-checked individually during authoring
(`test_stats_fixes.py` → `3 passed in 0.01s`, `test_storage_fixes.py` → `6 passed in 0.23s`) before
the final isolation run above; results were identical to their behaviour inside the full suite.

## FIRST Self-Check

| Property | Satisfied | How |
|---|---|---|
| Fast | ✅ | No sleeps, no network, no subprocesses. `export_report` tests are the only I/O and they write exclusively under pytest's `tmp_path`. Full 49-test suite runs in `0.11s` (measured above); the new 17 tests alone are a fraction of that. |
| Independent | ✅ | `test_stats_fixes.py` builds `Task` objects in memory per test, no fixtures needed. `test_storage_fixes.py` uses the `tmp_path` and `sample_tasks` fixtures (function-scoped, fresh per test) for all filesystem work — no fixed paths like `data/tasks.json`. `test_auth_fixes.py` uses `monkeypatch.setenv`/`delenv` for `TASKTRACKER_ADMIN_TOKEN`, which pytest reverts automatically after each test, so no test's environment leaks into another. `test_auth_fixes.py` passed standalone (`8 passed in 0.02s`, shown above). |
| Repeatable | ✅ | All `created_at`/`completed_at` values are hardcoded ISO dates (e.g. `"2026-01-01"`); no test calls `date.today()` or relies on the current date. No randomness, no network, no dependence on CWD or host filesystem layout beyond `tmp_path`. |
| Self-validating | ✅ | Every assertion is an exact expected value (`== 0.0`, `== [2, 4, 3, 1]`, `== 4.0`, `is False`, `is True`) or `pytest.raises(ExpectedError, match=...)` / `str(excinfo.value) == "..."` for error paths. No test asserts only truthiness. |
| Timely | ✅ | One test file per changed module, one regression test per defect in `fix-summary.md` (S1, S2, S3.2/F4, S3a, S3b), each confirmed above to fail against the documented "Before" snippet by direct code-level reasoning (no test asserts behaviour the baseline suite already covers). |

No `⚠️` entries.

## Coverage Gaps

- **Constant-time property of `hmac.compare_digest`**: a unit test cannot observe timing behaviour
  without violating the Fast property (would require statistical timing measurement over many
  iterations, which is slow and flaky by nature). Instead, `test_verify_admin_token_returns_true_for_matching_token`
  and `test_verify_admin_token_returns_false_for_wrong_token` verify the *functional* correctness of
  the comparison (accepts the right token, rejects the wrong one); the use of `hmac.compare_digest`
  itself is verifiable by code inspection, as `fix-summary.md`'s Manual Verification section already
  did for the related non-echoing message.
- **`list_tasks` default `sort="created"` branch**: unchanged by this fix and already covered by
  `tests/test_storage.py::test_default_listing_is_ordered_by_creation`; not re-tested here per the
  scope rule.
- Everything else in scope (S1, S2, S3.2/F4, S3a, S3b) has regression + boundary + neighbour
  coverage as tabulated above.

## References

**Files read**: `context/bugs/BUG-001/fix-summary.md`, `tests/conftest.py`, `tests/test_stats.py`,
`tests/test_storage.py`, `tests/test_cli.py`, `src/stats.py`, `src/storage.py`, `src/auth.py`,
`src/models.py`, `pytest.ini`.

**Files created**: `tests/test_stats_fixes.py`, `tests/test_storage_fixes.py`,
`tests/test_auth_fixes.py`, `context/bugs/BUG-001/test-report.md`.

**Commands run**:
- `python3 -m pytest` (baseline reproduction) → `32 passed in 0.30s`
- `python3 -m pytest -v` (after adding new tests) → `49 passed in 0.11s`
- `python3 -m pytest tests/test_auth_fixes.py -v` (isolation run, final) → `8 passed in 0.02s`
- `python3 -m pytest tests/test_stats_fixes.py -v` (isolation spot-check) → `3 passed in 0.01s`
- `python3 -m pytest tests/test_storage_fixes.py -v` (isolation spot-check) → `6 passed in 0.23s`
