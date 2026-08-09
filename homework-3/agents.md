# `agents.md` — AI Agent Operating Guide for the Virtual Cards Service

> **Author / Student**: Simon Darienko · **Homework 3** · Companion to [`specification.md`](./specification.md)
> **Applies to**: any AI coding agent (Claude Code, Copilot, Cursor, Codex) working in this repository.
> **Precedence**: `specification.md` (what to build) → this file (how to behave) → `.cursor/rules/` (editor-level enforcement) → model defaults. If two sources conflict, the **more restrictive** rule wins, and you flag the conflict in your response.

---

## 0. The one-paragraph version

You are working on an **issuer-side virtual card platform in a regulated environment**. Money is integer minor units, never floats. Card numbers never enter this codebase — not in code, tests, fixtures, logs, comments or commit messages. Every state change is idempotent, optimistically locked and audited in the same transaction. When you are uncertain whether something is allowed, **deny/decline** and say so. When the spec does not answer a question, **stop and ask** — do not invent a requirement and do not silently widen scope.

---

## 1. Tech stack assumptions

Do not introduce alternatives to these without an explicit instruction.

| Layer | Choice | Notes |
|---|---|---|
| Language | **Python 3.12** | Full type annotations; `from __future__ import annotations` not needed on 3.12 |
| Web framework | **FastAPI** + Pydantic v2 | `model_config = ConfigDict(extra="forbid")` on every request model |
| Persistence | **PostgreSQL 16** + SQLAlchemy 2.0 (async) + Alembic | No ORM lazy-loading across request boundaries |
| Cache / counters | **Redis 7** | Accelerator and rate-limit store only — **never** the source of truth for card status |
| Testing | **pytest**, `pytest-asyncio`, **Hypothesis**, `testcontainers` for DB/Redis | Fakes over mocks for the processor port |
| Quality | **ruff** (lint + format), **mypy --strict**, `bandit`, `pip-audit` | All must pass before you claim a task is done |
| Observability | structlog (JSON), OpenTelemetry, Prometheus client | Log keys are allow-listed |
| Async work | In-process scheduler + transactional outbox relay | No hidden background threads in request handlers |

**Dependency policy**: adding a third-party dependency requires justification in the PR description (what it replaces, why hand-rolling is worse, licence, maintenance signal). Never add a dependency that touches card data, cryptography primitives, or authentication — use the platform-approved libraries already present.

---

## 2. Domain rules you must never violate

These map 1:1 to the `IN-*` guardrails in `specification.md` §6.

1. **Money** — integer `amount_minor` + ISO-4217 `currency`. `float` for money is a bug, including in tests and log strings. No cross-currency arithmetic. Use the `Money` value object; do not re-implement it locally.
2. **No PAN, ever** — the identifiers `pan`, `card_number`, `cardnumber`, `cvv`, `cvc`, `track2` may not appear as a field, column, variable, log key, fixture value or docstring example. Display is `pan_last4` only. Card credentials live with the processor; the reveal flow is processor-hosted.
3. **Card status changes only through the state machine** (`app/domain/state_machine.py`). If you find yourself writing `card.status = ...` anywhere else, you are doing it wrong — extend the transition table instead.
4. **Every mutation is idempotent** — accept and honour `Idempotency-Key`; same key + different body is a `409`, never a silent overwrite.
5. **Every mutation is audited in the same DB transaction** as the change. If the audit write cannot happen, the business change must not happen.
6. **Optimistic locking** on `VirtualCard` and `SpendingControl`; lost updates surface as `409 concurrent_modification`, never as last-write-wins.
7. **Fail closed** — unknown card status, missing controls, unavailable dependency, expired token, unreadable config: the answer is *decline / deny*. There is no permissive default branch anywhere on the authorization path.
8. **Time is UTC** internally, RFC 3339 on the wire; business windows use the account timezone and the timezone used for a decision is persisted with it.
9. **Least privilege by default** — a new endpoint starts with no access and gains exactly the scopes it needs. `404` (not `403`) for resources the caller may not know exist.
10. **Dual control** for administrative lock/release/close. Requester ≠ approver, enforced in code.

---

## 3. Code style and structure

- **Layering**: `api → services → domain`, with `infrastructure` and `adapters` injected. `app/domain/` imports **nothing** from `app/infrastructure/` or `app/api/` — this is enforced by an architecture test; do not "temporarily" break it.
- **Pure core**: decision logic (`decide()`, validators, the state machine) is pure — no I/O, no `datetime.now()` (inject a `Clock`), no randomness (inject a generator). This is what makes the hot path testable and the audit reproducible.
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `SCREAMING_SNAKE` for constants. Money fields end in `_minor` (`daily_limit_minor`). Timestamps end in `_at`. Booleans read as assertions (`is_active`, `requires_approval`), never `flag`/`status_bool`.
- **Functions**: prefer ≤ 40 lines and one reason to change. Early-return over nested conditionals. No boolean parameters that switch behavior — write two functions.
- **Typing**: `mypy --strict` clean. No bare `Any`, no `# type: ignore` without a comment explaining why and a linked issue.
- **Errors**: raise a typed `AppError` with an `ErrorCode` from the closed catalog. Never `raise Exception(...)`, never swallow an exception with a bare `except:`, never return `None` to signal failure on a path where `None` is also a legitimate value.
- **Comments**: explain *why*, not *what*. Regulatory or scheme-driven constraints deserve a comment with a reference (e.g. `# PSD2 SCA: assertion must be < 120s old — spec NFR-02`).
- **Commits**: conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`), imperative mood, one logical change per commit. Reference the task id: `feat(cards): add freeze endpoint (T-12)`.
- **No dead code, no commented-out code, no TODOs without an owner and an issue link.**

---

## 4. Testing and verification expectations

**You do not get to say "done" without evidence.** Before claiming a task complete, run the checks and paste the actual output.

| Requirement | Detail |
|---|---|
| **Write tests first** for domain logic and for every bug fix (a failing test that reproduces the bug, then the fix). |
| **Coverage** | ≥ 90 % overall; **100 % branch coverage** on `app/domain/state_machine.py`, `app/domain/authorization.py`, `app/domain/money.py` and the idempotency middleware. Coverage is a floor, not a goal — an untested branch on the decision path is a release blocker. |
| **Every edge case in §9 of the spec has a test** named after its id (`test_ec_09_concurrent_authorizations_share_one_daily_cap`). If you implement a task, implement its `EC-*` tests too. |
| **Concurrency tests** run ≥ 100 iterations and must be deterministic. A flaky concurrency test is treated as a real bug in the code, never as "just flaky" — do not add retries or `sleep` to make it pass. |
| **Acceptance criteria** | Each task in the spec has checkboxes. Reproduce them in the PR description with evidence (test names + output), not with "looks good". |
| **No network in unit/integration tests** — the processor is the fake adapter; sandbox calls run only in the nightly contract job. |
| **Fixtures** use processor test PANs only. A fixture containing a Luhn-valid non-test PAN fails the pipeline. Never copy production data anywhere. |
| **Performance claims require a measurement.** If a task references a `PERF-*` target, either run the load scenario or state explicitly that it is unverified. |

**Verification before completion is mandatory**: run `ruff check`, `mypy`, `pytest`, and the security tests. If any fail, report the failure — do not describe the work as complete, and do not weaken a test to make it pass.

---

## 5. Security and compliance constraints

**Hard rules** (violating one is a security incident, not a code-review nit):

- Never log, print, serialize into an error, include in a trace attribute, or write to a fixture: PAN, CVV, reveal tokens, session tokens, processor API keys, full step-up assertions.
- Never disable, weaken or bypass: signature verification on webhooks, the redaction filter, the authorization matrix, rate limits, the maker-checker check. If a test is inconvenient because of one of these, the test is wrong.
- Never widen an error message to include upstream exception text — it leaks internals to the customer.
- Never introduce a code path where an authorization decision can be `APPROVE` by default, by timeout, or by exception handler.
- Never store secrets in the repository, in `.env` committed files, in test fixtures, or in commit messages. If you believe you have seen a real secret, stop and report it.
- Never generate synthetic "realistic" customer data that could be mistaken for real personal data. Use obvious test markers (`cus_test_*`, `Test Customer 01`).
- Never add an endpoint, field, or export that returns more data than the caller needs (`ops` responses are masked by construction).
- Never make a destructive or irreversible change (dropping a column, deleting rows, rotating a key, closing cards in bulk) without an explicit instruction. Migrations are expand → migrate → contract across releases.

**Compliance behaviours** you should apply proactively:

- If a change affects what is stored, logged, retained or exported, update `docs/data-map.md` and `docs/audit-events.md` in the same PR.
- If a change alters the PCI boundary (anything touching the reveal flow or processor tokens), say so explicitly in the PR description and request a security review — do not merge on a normal approval.
- If a change adds a new mutating endpoint, add its audit action, its authorization-matrix rows and its rate-limit bucket in the same PR. The build should fail if you forget; do not "fix" the build by relaxing the check.

---

## 6. How to treat edge cases

This is the behaviour that separates an acceptable agent from a dangerous one in this domain.

1. **Enumerate before you implement.** For any new flow, list the empty state, the duplicate, the concurrent, the out-of-order, the partial-failure and the permission-boundary case. If the spec §9 covers it, follow the spec. If it does not, add it to §9 in your PR and state the chosen behavior.
2. **Prefer explicit refusal to clever inference.** An ambiguous limit value (`0`), an unknown MCC, a currency mismatch, an unrecognised status → typed error with a stable code. Never guess the customer's intent with money.
3. **Idempotent by construction.** Ask "what happens if this runs twice?" for every handler, job and event consumer, and make the second run a provable no-op.
4. **Duplicates and out-of-order events are normal, not exceptional.** Every event consumer dedupes on the processor's event id and tolerates arrival order. Never assume `AUTH` precedes `CAPTURE`.
5. **Partial failure needs a named outcome.** "Local succeeded, remote failed" must have a documented resolution (retry, compensate, diverge-and-reconcile) — never an unhandled exception and never a silent inconsistency.
6. **Errors are user-visible artifacts.** Customer-facing text is generic and non-revealing (`"declined for security reasons"`); internal detail lives in the audit record and the log. Never leak fraud-rule names, velocity thresholds or the existence of another customer's data.
7. **Never retroactively change a settled fact.** Lowering a limit affects the future only. Corrections are new append-only rows, not updates.
8. **Boundaries get their own tests**: expiry ± 1 second, cap exactly reached, DST transition, the 100th and 101st page item, token at TTL.

---

## 7. Working agreement — how to run a task

1. **Read the task in `specification.md`** (`T-nn`), its `Serves` objectives and its acceptance criteria. Read the `IN-*` guardrails and the `EC-*` rows it maps to in §12.
2. **Restate the plan in 3–6 bullets** before writing code, including which files you will touch and which tests you will add. If the task requires a decision the spec does not make, ask **before** coding.
3. **Write the failing tests**, then the implementation, then run the full check suite.
4. **Report with evidence**: what you changed, the acceptance checkboxes with proof, what you did *not* do, and any assumption you had to make.
5. **Keep the diff scoped.** Unrelated refactors, formatting sweeps and dependency bumps go in separate PRs. Do not "improve" code outside the task.
6. **Stop and ask** when: the spec is silent or contradictory, a change would alter the PCI boundary or the audit chain, a test can only pass by weakening a control, or the task appears to require handling real card data.

**Never do without explicit approval**: `git push --force`, rewriting history, committing to `main`, editing `.github/workflows/*` security steps, changing migration files that have already been applied, disabling a CI gate, deleting tests.

---

## 8. Definition of done (checklist to paste into every PR)

- [ ] Implements exactly one `T-nn`; task id in the PR title
- [ ] All acceptance criteria from the task ticked, with evidence
- [ ] `EC-*` cases mapped to this task have named tests
- [ ] `ruff check` · `ruff format --check` · `mypy --strict` · `pytest` all pass (output pasted)
- [ ] Coverage floor respected; 100 % branch on the critical modules if touched
- [ ] New/changed mutating endpoint has: audit action, authorization-matrix rows, rate-limit bucket, idempotency support
- [ ] No PAN-shaped data anywhere (redaction test passes); no new secret in the repo
- [ ] Docs updated where relevant (`data-map.md`, `audit-events.md`, `errors.md`, runbooks)
- [ ] Migration is reversible and additive
- [ ] Assumptions and open questions stated explicitly
