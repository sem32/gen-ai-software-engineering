---
name: unit-tests-FIRST
description: Use when generating or reviewing unit tests - defines the FIRST properties (Fast, Independent, Repeatable, Self-validating, Timely) with concrete pytest rules and the self-check table every test report must contain
applies_to: unit-test-generator.agent.md
---

# FIRST — the five properties of a good unit test

Every test you generate must satisfy all five. A test that violates one is worse than no test: it
either lies about the code or it trains the team to ignore the suite.

## F — Fast

A unit test runs in milliseconds, so the whole suite runs on every save.

**Do**: call functions directly; build objects in memory; use `tmp_path` for the rare test that
genuinely needs a file.
**Don't**: sleep, open sockets, spawn subprocesses when an in-process call exists, or loop over
thousands of generated cases to make a point that three cases make.

Budget: the full suite stays under a second on this project. If one test needs more, it is not a
unit test.

## I — Independent

Each test passes alone, and passes in any order, with no shared mutable state.

**Do**: get state from fixtures (`tmp_path`, `store`, `sample_tasks`); create exactly the data the
test needs; use `monkeypatch` for environment variables so it is undone automatically.
**Don't**: write to a fixed path like `data/tasks.json`; depend on a task created by an earlier test;
mutate a module-level or session-scoped object; rely on test execution order or on `-p no:randomly`.

Check: `python3 -m pytest tests/test_x.py::test_one` must pass on its own.

## R — Repeatable

Same code, same result — on any machine, any day, offline.

**Do**: pin dates explicitly (`created_at="2026-01-01"`); inject the clock or accept both endpoints
of a boundary; assert on structure rather than on locale- or hash-dependent ordering.
**Don't**: call `date.today()` inside an assertion, use random data without a fixed seed, depend on
the host filesystem layout, the current working directory, network access, or an environment variable
the test did not set itself.

## S — Self-validating

The test decides pass/fail by itself. No human reads the output to judge.

**Do**: assert a specific expected value (`== 4.0`, `== [1, 2, 3]`); use
`pytest.raises(ExpectedError)` with a message check for error paths; assert on the returned exit code
and on the side effect (file written, file *not* written).
**Don't**: `print()` and eyeball it, assert only `is not None` or `assert result`, wrap the assertion
in a conditional, or catch the exception you are trying to detect.

## T — Timely

The test arrives with the change it covers, and it covers **that** change.

**Do**: write one test per fixed defect that fails against the pre-fix behaviour and passes after —
the regression test *is* the proof the fix works; cover the boundary that broke (empty collection,
`..` in a path, the tie in a sort order) and the neighbouring case that must keep working.
**Don't**: re-test what the existing suite already covers, add tests for untouched modules, or test
private helpers instead of the public behaviour that the bug report described.

Scope rule: tests are generated **only** for the code the fix changed, as listed in
`fix-summary.md`.

## Naming and layout

- New file per changed module: `tests/test_<module>_fixes.py`. Never edit or overwrite an existing
  test file — the baseline suite is evidence and must stay untouched.
- Test names state the expected behaviour: `test_stats_on_store_without_completed_tasks_returns_zero`,
  not `test_stats_2`.
- One behaviour per test. Use `@pytest.mark.parametrize` for the same behaviour across inputs, not to
  fold unrelated assertions together.
- Reuse the fixtures in `tests/conftest.py` instead of re-inventing them.

## Mandatory self-check in the report

`test-report.md` must contain this table, filled in with a concrete justification per property —
naming the test or fixture that makes it true, not the word "yes".

| Property | Satisfied | How |
|---|---|---|
| Fast | ✅ / ⚠️ | e.g. "no I/O outside `tmp_path`; suite runs in 0.14s (measured)" |
| Independent | ✅ / ⚠️ | e.g. "every test takes its store from the `store_path` fixture; env set via `monkeypatch`" |
| Repeatable | ✅ / ⚠️ | e.g. "all dates hardcoded; no network, no `date.today()` in assertions" |
| Self-validating | ✅ / ⚠️ | e.g. "exact expected values; error paths use `pytest.raises` with message match" |
| Timely | ✅ / ⚠️ | e.g. "one regression test per defect in `fix-summary.md`; each was confirmed to fail pre-fix" |

Any `⚠️` must be followed by a sentence explaining why the compromise was unavoidable.

Also record, for each generated test, the **pre-fix verdict**: state whether the test would have
failed against the original code and how you established that (reasoning against the documented
"before" snippet in `fix-summary.md`, or by re-running the test against the old behaviour).
