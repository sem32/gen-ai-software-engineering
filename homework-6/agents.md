# `agents.md` — AI Agent Operating Guide for the Multi-Agent Banking Pipeline

> **Author / Student**: Simon Darienko · **Homework 6 (Capstone)** · Companion to
> [`specification.md`](./specification.md)
> **Applies to**: any AI coding agent (Claude Code, Copilot, Cursor, Codex) working in `homework-6/`.
> **Precedence**: `specification.md` (*what* to build) → this file (*how* to behave) →
> `.claude/settings.json` (mechanical enforcement) → model defaults. If two sources conflict, the
> **more restrictive** rule wins and you flag the conflict in your response.

---

## 0. The one-paragraph version

You are building a **file-based multi-agent transaction pipeline for a regulated banking context**.
Money is `decimal.Decimal` parsed from strings, never `float`. Account numbers are PII and appear
masked (`****1001`) everywhere outside the process. Agents never call each other — they exchange JSON
messages through `shared/`. Every decision is written to an append-only audit trail before the result
file is produced. When a decision path hits missing or unparseable data, the answer is **reject or
hold**, never "approve anyway". When the spec does not answer a question, **stop and ask** — do not
invent a requirement and do not widen scope.

---

## 1. The four meta-agents of this assignment

This project is built *by* four AI agents, each with a distinct deliverable. Know which one you are.

| Meta-agent | Deliverable | Its "plus" | Where it lives |
|---|---|---|---|
| **Agent 1 — Specification** | `specification.md`, `agents.md` | **Skill**: `/write-spec` slash command that renders the template | `.claude/commands/write-spec.md` |
| **Agent 2 — Code generation** | `integrator.py`, `agents/*.py`, `mcp/server.py` | **MCP context7**: framework lookups documented in `research-notes.md` | `.claude/commands/run-pipeline.md`, `research-notes.md` |
| **Agent 3 — Unit tests** | `tests/*`, `scripts/coverage_gate.py` | **Hook**: blocks `git push` when coverage < 80 % | `.claude/settings.json` |
| **Agent 4 — Documentation** | `README.md`, `HOWTORUN.md` | **Requirement**: README carries the author's name | `README.md` |

The **runtime** agents (validator, fraud detector, compliance checker, settlement processor,
reporting agent) are the *output* of Agent 2 — do not confuse the two layers when reading a task.

---

## 2. Tech stack assumptions

Do not introduce alternatives without an explicit instruction.

| Layer | Choice | Notes |
|---|---|---|
| Language | **Python 3.12+** (developed on 3.14) | Full type annotations; `from __future__ import annotations` at the top of every module |
| Pipeline dependencies | **standard library only** | `decimal`, `pathlib`, `json`, `uuid`, `datetime`, `re`, `argparse` |
| Testing | **pytest** + **pytest-cov** | `tmp_path` for isolation; no network, no sleeping, no real `shared/` |
| MCP | **fastmcp ≥ 2** (custom server) · **@upstash/context7-mcp** (docs) | `fastmcp` is imported only by `mcp/server.py` |
| Environment | project-local `.venv/` | never install into the system interpreter |

**Dependency policy**: adding a runtime dependency to the pipeline requires justification (what it
replaces, why the standard library is worse). The pipeline must stay runnable with a bare Python
install — that is a deliberate property, not an accident.

---

## 3. Domain rules you must never violate

These map 1:1 to the `IN-*` guardrails in `specification.md` §6.

1. **Money** — `Decimal` constructed from `str`, quantised `ROUND_HALF_UP` to the currency's minor
   unit. `float` in a money path is a bug, including in tests and log strings. `Decimal(1.1)` is the
   same bug wearing a `Decimal` costume. No cross-currency arithmetic; USD-equivalence is for
   threshold *comparisons* only and never becomes a settled figure.
2. **No plaintext PII** — `source_account`, `destination_account` and `description` never leave the
   process unmasked. `mask_account()` is the only way an account reaches a log, a report, the console
   or an MCP response. `description` is not logged at all.
3. **Fail closed** — missing `fraud` section, unknown currency, unparseable timestamp, absent
   country: the answer is *reject* or *hold*. There is no permissive `else` branch on a decision path.
4. **Additive `data`** — an agent adds its own section (`validation` / `fraud` / `compliance` /
   `settlement`) and updates `status`. It never deletes another agent's section and never edits
   `amount` after validation has normalised it.
5. **Exactly-once terminal outcome** — every transaction ends in `shared/results/` with a status from
   the closed set `{rejected, held, settled}`, written once.
6. **Audit before result** — the audit record is appended *before* the terminal file is written, so a
   crash between the two leaves evidence rather than silence.
7. **Pure decision functions** — `validate()`, `score()`, `screen()`, `settle()` read no wall clock
   and generate no randomness. Time comes from the transaction; UUIDs and timestamps are minted in
   the protocol layer at message-build time.
8. **Claim before work** — a message is moved into `processing/` before it is processed, so it can
   never be picked up twice.
9. **Illustrative fixtures are labelled** — the sanctions list, the watchlist and the FX rate table
   carry a comment saying they are demonstration data, not a screening feed.

---

## 4. Code style and structure

- **Layering**: `integrator.py → agents/<agent>.py → agents/base.py → agents/protocol.py`.
  `protocol.py` imports nothing from the agents; agents import nothing from the integrator. The MCP
  server imports only `agents/results_store.py`.
- **One agent per module**, one class per agent, `process_message(message: dict) -> dict` as the
  single entry point. The class holds no mutable state between messages beyond its workspace handle.
- **Naming**: `snake_case` functions and variables, `PascalCase` classes, `SCREAMING_SNAKE`
  constants. Rule codes and rejection codes are stable lowercase strings with `:` for the parameter
  (`unknown_currency:XYZ`) — they are part of the contract and tests assert on them.
- **Functions**: prefer ≤ 40 lines and one reason to change. Early-return over nested conditionals.
  No boolean parameters that switch behaviour — write two functions.
- **Errors**: raise the module's typed error (`ProtocolError`, `MoneyError`). Never `raise
  Exception(...)`, never a bare `except:`, never `return None` to signal failure where `None` is also
  a legitimate value.
- **Comments** explain *why*, not *what*. Regulatory constraints get a reference
  (`# FinCEN CTR threshold — spec MO-3`).
- **No dead code, no commented-out code, no TODO without an owner.**
- **Commits**: conventional commits, imperative mood, one logical change each, referencing the task
  id — `feat(hw6): add fraud detector scoring rules (T-2)`.

---

## 5. Testing and verification expectations

**You do not get to say "done" without evidence.** Run the checks and paste the actual output.

| Requirement | Detail |
|---|---|
| **Coverage** | Gate at **80 %** (the hook blocks `git push` below it); the suite targets **≥ 90 %**. Coverage is a floor, not a goal — an untested branch on a decision path is a release blocker. |
| **Every `EC-*` case has a test** named after its id, e.g. `test_ec_02_unknown_currency_is_rejected`. Implementing a task means implementing its edge-case tests too. |
| **Isolation** | Tests use `tmp_path`. A test that writes into the repository's real `shared/` is a broken test, even if it passes. |
| **Determinism** | No `sleep`, no network, no dependence on the current date. If a test needs "today", inject it. |
| **Integration test** | One test runs the full pipeline against the real `sample-transactions.json` and asserts the §8 outcome table of the spec, transaction by transaction. |
| **Acceptance criteria** | Each task in the spec has checkboxes. Reproduce them with evidence (test names + output), not with "looks good". |

**Verification before completion is mandatory**: run `pytest --cov`, run `python integrator.py`, and
exercise the MCP server. If anything fails, report the failure — do not describe the work as
complete, and never weaken a test to make it pass.

---

## 6. Security and compliance constraints

**Hard rules** — violating one is an incident, not a review nit:

- Never log, print, serialise into an error, or write into a fixture: a full account number, a holder
  name, or a customer-supplied description.
- Never disable or weaken: the redaction in `AuditLogger`, the fail-closed branches, the closed
  status set, the coverage gate.
- Never widen an error message with upstream exception text on a customer-facing path.
- Never introduce a code path where a transaction can reach `settled` without passing validation,
  fraud scoring and compliance screening in that order.
- Never commit a secret. There are none in this project and there should never be one — if you
  believe you have seen a real one, stop and report it.
- Never generate "realistic" customer data. Accounts are `ACC-nnnn`, names are absent by design.
- Never make a destructive change outside `shared/` without an explicit instruction. `shared/` is
  disposable by contract; everything else is not.

**Proactive behaviours**: if a change alters what is stored, logged or exported, update
`specification.md` §3.4 and the README in the same change. If a change adds a status, add it to the
closed set, to the reporting aggregation and to the integration test in the same change.

---

## 7. How to treat edge cases

1. **Enumerate before you implement.** For any new flow list the empty case, the duplicate, the
   out-of-order, the partial failure and the boundary. If `specification.md` §7 covers it, follow the
   spec. If it does not, add a row to §7 in the same change and state the chosen behaviour.
2. **Prefer explicit refusal to clever inference.** An unknown currency, an unparseable amount, an
   unrecognised transaction type → stable error code. Never guess the customer's intent with money.
3. **Report every failing check, not the first.** A rejected transaction gets one round trip with a
   complete reason list.
4. **Boundaries get their own tests**: exactly 10 000.00, exactly 9 000.00, 05:59:59 vs 06:00:00 UTC,
   the fee floor at 200.00 and the fee cap at 10 000.00, Friday → Tuesday rollover.
5. **Partial failure needs a named outcome.** A malformed inbox file is quarantined with an audit
   entry and the run continues — never an unhandled traceback, never a silent skip.
6. **Never retroactively change a settled fact.** A correction is a new result record, not an edit.

---

## 8. Working agreement — how to run a task

1. **Read the task in `specification.md`** (`T-n`), its acceptance criteria, the `IN-*` guardrails and
   the `EC-*` rows it touches.
2. **Restate the plan in 3–6 bullets** before writing code: which files, which tests. If the task
   requires a decision the spec does not make, ask **before** coding.
3. **Write the failing tests, then the implementation**, then run the full check suite.
4. **Report with evidence**: what changed, acceptance checkboxes with proof, what you did *not* do,
   and every assumption you had to make.
5. **Keep the diff scoped.** Unrelated refactors and formatting sweeps go in a separate change.
6. **Stop and ask** when: the spec is silent or contradictory, a change would weaken the audit trail
   or the PII masking, or a test can only pass by relaxing a control.

**Never without explicit approval**: `git push --force`, rewriting history, committing to `main`,
disabling the coverage hook, deleting tests, editing `sample-transactions.json`.

---

## 9. Definition of done (paste into every PR)

- [ ] Implements exactly one `T-n`; task id in the PR title
- [ ] All acceptance criteria ticked, with pasted evidence
- [ ] `EC-*` cases mapped to this task have named tests
- [ ] `pytest --cov` passes with coverage ≥ 90 % (output pasted)
- [ ] `python integrator.py` exits 0 and reconciles input count to result count
- [ ] No `float` in a money path; no unmasked account anywhere in output
- [ ] Spec/README updated if behaviour, storage or logging changed
- [ ] Assumptions and open questions stated explicitly
