---
description: Test-first workflow, coverage floors, concurrency testing and evidence-based completion claims
globs: ["tests/**/*.py", "app/**/*.py"]
alwaysApply: false
---

# Testing and verification

## Order of work

1. Restate the task plan in 3–6 bullets (files to touch, tests to add) **before** writing code.
2. Write the failing test.
3. Write the minimum implementation that passes it.
4. Run the full check suite and paste real output.

For a bug fix, step 2 is a test that **reproduces the bug**. A fix without a reproducing test is not a fix.

## Coverage floors

- ≥ 90 % overall.
- **100 % branch coverage** on `app/domain/state_machine.py`, `app/domain/authorization.py`, `app/domain/money.py`, `app/api/middleware/idempotency.py`.
- Every `EC-*` row in `specification.md` §9 that maps to your task has a test named after its id.
- Every `CardStatus` member has an explicit branch in `decide()` — exhaustiveness is asserted by a test, not assumed.

## Test rules

- **No network** in unit or integration tests. The card processor is the fake adapter (`app/adapters/fake_processor`), which can inject `latency`, `timeout`, `http_500`, `duplicate_webhook`, `out_of_order_webhook`, `reject_provisioning`.
- Prefer **fakes over mocks**. Asserting on mock call counts tests your own wiring; a fake tests behavior.
- **Concurrency tests run ≥ 100 iterations and must be deterministic.** A flaky concurrency test is a real race in the code. Never "fix" it with `sleep`, retries, or by lowering the iteration count.
- **Time is injected.** No test may depend on the wall clock; freeze the clock and test the boundaries explicitly (expiry ± 1 s, cap exactly reached, DST transition, token at TTL, page item 100 and 101).
- **Fixtures use processor test PANs only** and obvious test markers (`cus_test_*`, `Test Customer 01`). A Luhn-valid non-test PAN in a fixture fails the pipeline. Production data is never copied into any environment.
- Property-based tests (Hypothesis) for money arithmetic and for auth/capture/reversal sequences: counters must never go negative and never exceed the sum of authorizations.

## Evidence before assertions

Do **not** write "done", "fixed", "should work" or "tests pass" without having run:

```
ruff check . && ruff format --check .
mypy --strict app
pytest -q
pytest -q tests/security
```

Paste the output. If something fails, report the failure — do not weaken a test, mark it `xfail`, or narrow its assertions to make it green. If a `PERF-*` target is referenced by the task, either run the load scenario or state explicitly that it is unverified.

## PR checklist (paste and tick)

- [ ] One `T-nn` per PR, task id in the title
- [ ] Acceptance criteria from the task, each with evidence
- [ ] `EC-*` tests present and named after their ids
- [ ] Lint, types, tests, security tests all green (output pasted)
- [ ] Coverage floors respected
- [ ] Docs updated (`data-map.md`, `audit-events.md`, `errors.md`, runbooks) where relevant
- [ ] Migration additive and reversible
- [ ] Assumptions and open questions stated explicitly
