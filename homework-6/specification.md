# Multi-Agent Banking Transaction Pipeline — Specification

> **Author / Student**: Simon Darienko · **Homework 6 (Capstone)**
> **Produced by**: Agent 1 (Specification) — the `/write-spec` slash command in
> [`.claude/commands/write-spec.md`](.claude/commands/write-spec.md)
> **Companion documents**: [`agents.md`](agents.md) (how agents must behave) ·
> [`research-notes.md`](research-notes.md) (context7 research) ·
> [`README.md`](README.md) · [`HOWTORUN.md`](HOWTORUN.md)
>
> Ingest the information from this file, implement the Low-Level Tasks, and generate the code
> that will satisfy the High- and Mid-Level Objectives.

---

## 1. High-Level Objective

Build a file-based multi-agent pipeline that ingests raw banking transactions from
`sample-transactions.json`, passes them through validation, fraud scoring, compliance screening
and settlement as JSON messages on disk, and produces an auditable per-transaction outcome in
`shared/results/` plus a run summary report.

---

## 2. Mid-Level Objectives

Concrete and individually testable. Each one is referenced by task acceptance criteria in §5 and
by the edge-case table in §7.

| id | Objective |
|---|---|
| **MO-1** | Every record in `sample-transactions.json` reaches `shared/results/` with exactly one terminal status from the closed set `{rejected, held, settled}` — no record is lost, duplicated or left in an intermediate directory. |
| **MO-2** | Structurally invalid transactions (missing field, non-positive amount, non-ISO-4217 currency, malformed timestamp or account) are rejected by the validator and written to `shared/results/` with a machine-readable `rejection_reasons` list and a human-readable `rejection_reason` string. |
| **MO-3** | Transactions at or above **10 000 USD-equivalent** are flagged for fraud review with a numeric `risk_score` (0–100) and an itemised list of the rules that fired; the fraud detector never mutates the monetary amount. |
| **MO-4** | Every agent operation is appended to a single audit trail with an ISO 8601 UTC timestamp, the agent name, the transaction id and the outcome — and no account number, holder name or free-text description ever appears there in plaintext. |
| **MO-5** | All monetary arithmetic uses `decimal.Decimal` with explicit `ROUND_HALF_UP` quantisation to the currency's minor unit; `float` never touches an amount, a fee or a net figure — in production code, fixtures or tests. |
| **MO-6** | The pipeline is queryable after the fact: a FastMCP server exposes `get_transaction_status`, `list_pipeline_results` and the `pipeline://summary` resource, all reading the same `shared/results/` artefacts the pipeline wrote. |

---

## 3. Implementation Notes

### 3.1 Money

- Amounts arrive as **strings** in the source JSON and stay strings on the wire. They are parsed
  with `Decimal(str_value)` exactly once, at the validator boundary.
- `float` is a bug. `Decimal(1.1)` is also a bug — construct from `str` only.
- Rounding is always `ROUND_HALF_UP` via `quantize(Decimal("0.01"))` (or the currency's minor-unit
  exponent — JPY has 0 decimals, so `quantize(Decimal("1"))`).
- No cross-currency arithmetic. USD-equivalence for threshold checks uses an explicit, documented
  static rate table and is used **only** for comparisons, never for the settled figure.

### 3.2 Currency codes

- ISO 4217 alphabetic codes, upper case, validated against an explicit allow-list that also carries
  the number of minor units (`USD: 2`, `EUR: 2`, `GBP: 2`, `JPY: 0`, …).
- An unknown code is a rejection, not a warning. Never "best-effort" a currency.

### 3.3 Logging and audit trail

- One append-only JSONL audit file per run: `shared/audit/audit-log.jsonl`.
- Every record: `{"timestamp": <ISO 8601 UTC, Z-suffixed>, "agent": <name>, "transaction_id": <id>,
  "outcome": <string>, "detail": <object|null>}`.
- The audit trail is written **before** the terminal result file is produced, so a crash between the
  two leaves evidence, not silence.

### 3.4 PII

- `source_account`, `destination_account`, and any holder-identifying free text are **sensitive**.
- Accounts are masked to `****NNNN` (last four characters) everywhere they leave the process:
  audit log, console output, report, MCP responses.
- `description` is never logged and never copied into the audit trail — it is free text supplied by
  the customer and may contain names or references.
- Terminal result files under `shared/results/` keep the masked form only.

### 3.5 Message protocol

Agents never call each other directly. They communicate by writing JSON files into shared
directories. Every file is a single message of this shape:

```json
{
  "message_id": "uuid4-string",
  "timestamp": "2026-03-16T10:00:00Z",
  "source_agent": "transaction_validator",
  "target_agent": "fraud_detector",
  "message_type": "transaction",
  "data": {
    "transaction_id": "TXN001",
    "amount": "1500.00",
    "currency": "USD",
    "status": "validated"
  }
}
```

- `message_id` — UUID4, regenerated per hop.
- `timestamp` — ISO 8601 UTC with a `Z` suffix.
- `target_agent` — the next agent, or the sentinel `pipeline_results` for a terminal outcome.
- `data` accumulates: each agent adds its own section (`validation`, `fraud`, `compliance`,
  `settlement`) and updates `status`; no agent deletes another agent's section.

### 3.6 Directory contract

```
shared/
├── input/       ← integrator drops the initial messages here
├── processing/  ← an agent moves the message here while it works on it
├── output/      ← an agent writes the result here for the next agent
├── results/     ← terminal outcomes land here (one file per transaction)
├── reports/     ← pipeline run summary (JSON + Markdown)
└── audit/       ← append-only audit trail (JSONL)
```

A message is claimed by **moving** it into `processing/` before work starts, so a half-processed
message can never be picked up twice.

### 3.7 Stack and quality bar

| Layer | Choice |
|---|---|
| Language | Python 3.12+ (developed on 3.14), standard library only for the pipeline |
| Testing | `pytest` + `pytest-cov`, isolation via `tmp_path` |
| MCP | `fastmcp` ≥ 2 (custom server), `@upstash/context7-mcp` (documentation lookup) |
| Coverage | **gate at 80 %** (hook blocks push below it), target **≥ 90 %** |

No third-party runtime dependency for the pipeline itself — `Decimal`, `pathlib`, `json`, `uuid`
and `datetime` cover everything. `fastmcp` is required only by the MCP server.

---

## 4. Context

### 4.1 Beginning state

- `homework-6/sample-transactions.json` — 8 raw transaction records, amounts as strings, containing
  deliberately bad data (an invalid currency `XYZ`, a negative `refund` amount) and deliberately
  suspicious data (a 9 999.99 structuring candidate, a 75 000 wire, an 02:47 UTC submission).
- `homework-6/TASKS.md` — the assignment.
- No pipeline code, no shared directories, no tests.

### 4.2 Ending state

- `integrator.py` — orchestrator.
- `agents/` — `protocol.py`, `base.py`, `transaction_validator.py`, `fraud_detector.py`,
  `compliance_checker.py`, `settlement_processor.py`, `reporting_agent.py`, `results_store.py`.
- `mcp/server.py` — FastMCP server exposing the pipeline.
- `tests/` — unit tests per agent + an end-to-end integration test, **coverage ≥ 90 %**.
- `shared/results/` — 8 terminal result files after a run; `shared/reports/pipeline-summary.{json,md}`.
- `.claude/commands/` — `write-spec.md`, `run-pipeline.md`, `validate-transactions.md`.
- `.claude/settings.json` — coverage-gate hook that blocks `git push` below 80 %.
- `mcp.json`, `README.md`, `HOWTORUN.md`, `research-notes.md`, `docs/screenshots/`.

---

## 5. Low-Level Tasks

One entry per agent, in build order.

---

### T-0. Shared message protocol and audit logging

**Task:** Message protocol / Foundation

**Prompt:**
> "Create the shared protocol module for a file-based multi-agent banking pipeline. It must build and
> validate messages with the fields message_id (uuid4), timestamp (ISO 8601 UTC with Z),
> source_agent, target_agent, message_type and data. Add money helpers that parse amounts from
> strings into `decimal.Decimal` and quantise with ROUND_HALF_UP to the currency's minor unit — never
> use float. Add `mask_account` that reduces an account identifier to `****` plus its last four
> characters. Add an `AuditLogger` that appends JSONL records with an ISO 8601 UTC timestamp, agent
> name, transaction id and outcome, refusing to write unmasked account numbers. Add a `Workspace`
> helper that creates and clears the shared/ directory tree and moves message files between stages."

**File to CREATE:** `agents/protocol.py`

**Functions to CREATE:**
`build_message(source_agent, target_agent, message_type, data, *, message_id=None, timestamp=None) -> dict`,
`validate_message(message: dict) -> None`,
`parse_amount(raw: str) -> Decimal`,
`quantize_money(value: Decimal, currency: str) -> Decimal`,
`mask_account(account: str) -> str`,
`class AuditLogger`, `class Workspace`

**Details:**
- `validate_message` raises `ProtocolError` naming the offending field — it never silently repairs.
- `parse_amount` rejects `None`, empty strings, `NaN`, `Infinity` and anything `Decimal` cannot parse,
  raising `MoneyError`.
- `Workspace.claim(path)` moves a message file into `processing/` and returns the new path.
- Audit records are flushed on every write (`fsync` not required; `flush` is).

**Acceptance criteria:**
- [ ] `build_message` output passes `validate_message` and carries a fresh UUID4 each call.
- [ ] `parse_amount("1500.00") == Decimal("1500.00")`; `parse_amount(1500.0)` raises `MoneyError`.
- [ ] `quantize_money(Decimal("0.125"), "USD") == Decimal("0.13")` (half-up, not banker's rounding).
- [ ] `quantize_money(Decimal("1500.4"), "JPY") == Decimal("1500")`.
- [ ] `mask_account("ACC-1001") == "****1001"`.
- [ ] An audit record containing a raw account number raises rather than being written.

---

### T-1. Transaction Validator

**Task:** Transaction Validator

**Prompt:**
> "Implement the transaction_validator agent. It consumes messages from shared/input targeted at it,
> claims each one into shared/processing, and checks: all required fields present and non-empty; the
> amount parses as Decimal, is strictly positive and has no more decimal places than the currency's
> minor unit; the currency is a known ISO 4217 code; the timestamp is ISO 8601; source and destination
> accounts match `ACC-<4 digits>` and differ; the transaction type is in the known set. A valid
> transaction is forwarded to fraud_detector via shared/output with status `validated`; an invalid one
> is written straight to shared/results with status `rejected`, a `rejection_reasons` list of stable
> machine codes and a joined human-readable `rejection_reason`. Add a `--dry-run` CLI mode that reads
> sample-transactions.json and prints a table of total / valid / invalid plus reasons, without writing
> anything to shared/."

**File to CREATE:** `agents/transaction_validator.py`

**Functions to CREATE:**
`class TransactionValidator(BaseAgent)` with
`validate(transaction: dict) -> list[str]` and `process_message(message: dict) -> dict`;
module-level `dry_run(sample_path: Path) -> dict` and `main(argv=None) -> int`

**Details:**
- Rejection codes are stable strings: `missing_field:<name>`, `invalid_amount`,
  `non_positive_amount`, `too_many_decimal_places`, `unknown_currency:<code>`, `invalid_timestamp`,
  `invalid_account_format:<field>`, `same_source_and_destination`, `unknown_transaction_type:<type>`.
- **All** failing checks are reported, not just the first — a rejected transaction gets one round trip.
- The validator normalises the amount to the currency's minor unit and writes it back as a string.

**Acceptance criteria:**
- [ ] `TXN006` (currency `XYZ`) is rejected with `unknown_currency:XYZ`.
- [ ] `TXN007` (amount `-100.00`) is rejected with `non_positive_amount`.
- [ ] The other six sample transactions are forwarded with `status == "validated"`.
- [ ] `--dry-run` writes nothing under `shared/` and exits `0` with a printed table.

---

### T-2. Fraud Detector

**Task:** Fraud Detector

**Prompt:**
> "Implement the fraud_detector agent. It consumes validated messages, applies a table of independent
> scoring rules and produces a `fraud` section containing `risk_score` (0–100, capped),
> `risk_level` (low <30, medium 30–59, high ≥60), `review_required` and `triggered_rules` — each with
> its code, points and a short reason. Rules: high value ≥10 000 USD-equivalent (+40); very high value
> ≥50 000 (+20 more); structuring, i.e. 9 000 ≤ amount < 10 000 (+35); unusual timing, submitted
> between 00:00 and 06:00 UTC (+25); cross-border, i.e. the metadata country is outside the currency's
> home region (+20); off-hours automated channel, i.e. channel `api` during unusual hours (+15);
> destination on the internal watchlist (+30). `review_required` is true when the score is high OR the
> amount is at or above 10 000 USD-equivalent. The agent must not modify the amount. Forward every
> transaction to compliance_checker with status `flagged_for_review` or `fraud_cleared`."

**File to CREATE:** `agents/fraud_detector.py`

**Functions to CREATE:**
`class FraudDetector(BaseAgent)` with `score(transaction: dict) -> dict` and
`process_message(message: dict) -> dict`

**Details:**
- Each rule is a small pure function `(transaction, amount) -> RuleHit | None`; the rule table is a
  module constant so it can be asserted on directly in tests.
- Scoring is deterministic — no randomness, no wall-clock reads; the transaction's own `timestamp`
  drives the timing rules.

**Acceptance criteria:**
- [ ] `TXN005` (75 000 USD wire) scores ≥ 60 → `risk_level == "high"`, `review_required` true.
- [ ] `TXN003` (9 999.99) fires `structuring`.
- [ ] `TXN004` (02:47 UTC, `api` channel) fires `unusual_timing` **and** `off_hours_api`.
- [ ] `TXN001` (1 500 USD, business hours, domestic) scores 0 → `risk_level == "low"`.
- [ ] The `amount` field is byte-identical before and after scoring.

---

### T-3. Compliance Checker

**Task:** Compliance Checker

**Prompt:**
> "Implement the compliance_checker agent. It consumes fraud-scored messages and produces a
> `compliance` section with `decision` (`cleared` or `held`), `ctr_required`, `checks` (each check's
> code, passed flag and note) and `hold_reasons`. Rules: a transaction at or above 10 000
> USD-equivalent requires a Currency Transaction Report (`ctr_required` true — reporting duty, not a
> hold); a counterparty country on the sanctions list is an immediate hold; a destination account on
> the watchlist is a hold; anything the fraud detector marked `review_required` with a high risk level
> is held for manual review. A held transaction is terminal and goes to shared/results with status
> `held`; a cleared one goes to settlement_processor. Fail closed: if the country or the fraud section
> is missing, hold."

**File to CREATE:** `agents/compliance_checker.py`

**Functions to CREATE:**
`class ComplianceChecker(BaseAgent)` with `screen(transaction: dict) -> dict` and
`process_message(message: dict) -> dict`

**Details:**
- Sanctions list and watchlist are module constants with a comment explaining that they are
  illustrative fixtures, not a real screening feed.
- `usd_equivalent(amount, currency)` uses the static rate table from `protocol.py` and is used for
  the CTR threshold only.
- Missing `fraud` section → `hold_reasons = ["missing_fraud_assessment"]`. No permissive default.

**Acceptance criteria:**
- [ ] `TXN002` (25 000 USD) is `cleared` with `ctr_required` true.
- [ ] `TXN005` (high risk) is `held` with `hold_reasons == ["fraud_review_required"]`.
- [ ] A transaction whose `metadata.country` is `IR` is held with `sanctioned_country:IR`.
- [ ] A message without a `fraud` section is held, never cleared.

---

### T-4. Settlement Processor

**Task:** Settlement Processor

**Prompt:**
> "Implement the settlement_processor agent. It consumes compliance-cleared messages and produces a
> `settlement` section with `settlement_id` (`STL-<transaction_id>`), `fee`, `net_amount`,
> `value_date` and `settled_at`. The fee is 0.25 % of the amount, floored at 0.50 and capped at 25.00
> in the transaction currency, quantised ROUND_HALF_UP to the currency's minor unit; the net amount is
> amount minus fee. The value date is the transaction date plus 2 business days for `wire_transfer`
> and plus 1 business day otherwise, skipping Saturdays and Sundays. The result is terminal: write it
> to shared/results with status `settled`. All arithmetic uses Decimal."

**File to CREATE:** `agents/settlement_processor.py`

**Functions to CREATE:**
`class SettlementProcessor(BaseAgent)` with `settle(transaction: dict) -> dict` and
`process_message(message: dict) -> dict`; helpers `calculate_fee(amount, currency) -> Decimal` and
`next_business_day(start: date, days: int) -> date`

**Details:**
- `Decimal("0.0025")` — not `0.0025`.
- `fee + net_amount == amount` exactly, after quantisation; assert this invariant in the code.
- `value_date` is an ISO date string (`YYYY-MM-DD`), `settled_at` a full ISO 8601 UTC timestamp.

**Acceptance criteria:**
- [ ] 1 500.00 USD → fee `3.75`, net `1496.25`.
- [ ] 100.00 USD → fee `0.50` (floor applied), net `99.50`.
- [ ] 75 000.00 USD → fee `25.00` (cap applied).
- [ ] A Friday `wire_transfer` settles on the following Tuesday.
- [ ] `fee + net_amount == amount` for every sample transaction that settles.

---

### T-5. Reporting Agent

**Task:** Reporting Agent

**Prompt:**
> "Implement the reporting_agent. It reads every terminal result from shared/results, aggregates
> counts by status and by risk level, totals the settled and held volume per currency using Decimal,
> lists rejected transactions with their reasons, and writes shared/reports/pipeline-summary.json plus
> a human-readable pipeline-summary.md. Account numbers stay masked. It also returns the summary dict
> so the integrator can print it."

**File to CREATE:** `agents/reporting_agent.py`

**Functions to CREATE:**
`class ReportingAgent` with `build_summary() -> dict` and `run() -> dict`

**Details:**
- Totals are per currency — never sum different currencies into one number.
- The summary carries `generated_at`, `total_transactions`, `by_status`, `by_risk_level`,
  `volume_by_currency`, `rejected`, `held`, `settled`.

**Acceptance criteria:**
- [ ] Over the eight sample transactions the summary reports 8 total, 2 rejected, 1 held, 5 settled.
- [ ] Both `pipeline-summary.json` and `pipeline-summary.md` exist after a run.
- [ ] No unmasked account number appears in either file.

---

### T-6. Integrator / Orchestrator

**Task:** Integrator

**Prompt:**
> "Implement integrator.py. It creates the shared/ directory tree (clearing it first unless
> --no-reset), loads sample-transactions.json, drops one protocol message per record into
> shared/input targeted at transaction_validator, then runs the agents in order — validator, fraud
> detector, compliance checker, settlement processor — each draining its inbox, and finally runs the
> reporting agent. It prints a per-stage progress line and a final results table to stdout and exits
> non-zero if any transaction failed to reach a terminal state."

**File to CREATE:** `integrator.py`

**Functions to CREATE:** `run_pipeline(sample_path, shared_root, *, reset=True) -> dict`,
`main(argv=None) -> int`

**Details:**
- Stages run sequentially, not concurrently — a message must be at rest in `output/` before the next
  agent claims it. This keeps the file protocol observable and the run reproducible.
- Reconciliation check at the end: `len(results) == len(sample)` and `input/` + `output/` are empty.

**Acceptance criteria:**
- [ ] `python integrator.py` exits `0` and prints a table of eight transactions.
- [ ] `shared/results/` holds exactly eight files after the run.
- [ ] `shared/input/` and `shared/output/` are empty after the run.
- [ ] Re-running the pipeline twice in a row produces the same eight terminal statuses.

---

### T-7. Results store and FastMCP server

**Task:** MCP exposure

**Prompt:**
> "Create agents/results_store.py with pure read functions over shared/results and shared/reports:
> `get_transaction_status(transaction_id)`, `list_pipeline_results()` and `latest_summary_text()`.
> Then create mcp/server.py, a FastMCP server named `pipeline-status` that exposes
> `get_transaction_status` and `list_pipeline_results` as tools and `pipeline://summary` as a
> resource, delegating entirely to results_store. Keep the FastMCP import out of the shared package so
> the pipeline itself has no third-party dependency."

**Files to CREATE:** `agents/results_store.py`, `mcp/server.py`

**Functions to CREATE:**
`get_transaction_status(transaction_id: str, shared_root: Path | None = None) -> dict`,
`list_pipeline_results(shared_root: Path | None = None) -> dict`,
`latest_summary_text(shared_root: Path | None = None) -> str`

**Details:**
- An unknown transaction id returns `{"found": false, "transaction_id": ..., "message": ...}` — it is
  not an exception; the caller is an LLM and needs a readable answer.
- The `mcp/` directory deliberately contains no `__init__.py` so it can never shadow the installed
  `mcp` package; `server.py` appends (never prepends) the project root to `sys.path`.

**Acceptance criteria:**
- [ ] `get_transaction_status("TXN005")` returns status `held` after a run.
- [ ] `get_transaction_status("NOPE")` returns `found: false` without raising.
- [ ] `list_pipeline_results()` returns eight entries and per-status counts.
- [ ] Reading `pipeline://summary` through a FastMCP in-memory `Client` returns the Markdown summary.

---

### T-8. Test suite and coverage gate

**Task:** Unit tests (Agent 3) and coverage enforcement

**Prompt:**
> "Write a pytest suite covering every agent plus an end-to-end integration test that runs the whole
> pipeline against the real sample-transactions.json in a tmp_path workspace. Cover the money helpers,
> the protocol validation errors, every fraud rule, both compliance outcomes, the settlement fee floor
> and cap, business-day rollover, the reporting aggregation and the results store. Then add
> scripts/coverage_gate.py which runs pytest with coverage and exits non-zero when total coverage is
> below 80 %, and wire it as a Claude Code PreToolUse hook that blocks `git push`."

**Files to CREATE:** `tests/conftest.py`, `tests/test_protocol.py`, `tests/test_transaction_validator.py`,
`tests/test_fraud_detector.py`, `tests/test_compliance_checker.py`, `tests/test_settlement_processor.py`,
`tests/test_reporting_agent.py`, `tests/test_results_store.py`, `tests/test_integration.py`,
`scripts/coverage_gate.py`, `.claude/settings.json`, `pytest.ini`

**Details:**
- Tests never touch the repository's real `shared/` — every test gets a `tmp_path` workspace.
- `tests/` has no `__init__.py`, so pytest does not put the project root on `sys.path` ahead of
  site-packages; `conftest.py` **appends** the root instead.
- The gate is a floor at 80 %; the suite targets ≥ 90 %.

**Acceptance criteria:**
- [ ] `pytest --cov` reports ≥ 90 % total coverage.
- [ ] `python scripts/coverage_gate.py` exits `0` at ≥ 80 % and non-zero below it.
- [ ] The hook fires on `git push` and reports the measured percentage.

---

### T-9. Documentation (Agent 4)

**Task:** Documentation

**Prompt:**
> "Write README.md with the author's name (Simon Darienko), a two-paragraph description of what the
> system does, one bullet per agent, an ASCII architecture diagram of the pipeline flow and a tech
> stack table. Write HOWTORUN.md with numbered steps from clone to demo, including the MCP server and
> the coverage gate. Write research-notes.md documenting the context7 queries made during code
> generation with the library id returned and the insight applied."

**Files to CREATE:** `README.md`, `HOWTORUN.md`, `research-notes.md`

**Acceptance criteria:**
- [ ] README contains "Simon Darienko", the ASCII diagram and the tech-stack table.
- [ ] HOWTORUN has numbered steps from setup through pipeline run, tests, hook and MCP.
- [ ] research-notes documents ≥ 2 context7 queries with library id and applied insight.

---

## 6. Guardrails (IN-\*)

| id | Guardrail |
|---|---|
| **IN-1** | `float` must never appear in an arithmetic path involving money. Parse from `str` into `Decimal`. |
| **IN-2** | No account number, holder name or transaction description in plaintext in logs, reports, console output or MCP responses. |
| **IN-3** | Fail closed — a missing or unparseable input on a decision path produces a rejection or a hold, never an approval. |
| **IN-4** | An agent adds to `data`; it never removes or rewrites another agent's section, and never edits `amount` after validation. |
| **IN-5** | Every terminal outcome is written exactly once, to `shared/results/`, with a status from the closed set. |
| **IN-6** | Decision logic is pure: no wall-clock reads and no randomness inside `validate` / `score` / `screen` / `settle`. Time comes from the transaction; ids come from the protocol layer. |
| **IN-7** | Sanctions list, watchlist and FX rates are illustrative fixtures and are labelled as such in code. |

---

## 7. Edge cases (EC-\*)

| id | Case | Required behaviour |
|---|---|---|
| **EC-01** | Amount `-100.00` on a `refund` | Rejected — `non_positive_amount`. A refund is modelled as a positive amount with type `refund`. |
| **EC-02** | Currency `XYZ` | Rejected — `unknown_currency:XYZ`. Never coerced to USD. |
| **EC-03** | Amount `9999.99` | Accepted, but the `structuring` fraud rule fires. |
| **EC-04** | Amount with 3+ decimals in a 2-minor-unit currency | Rejected — `too_many_decimal_places`. |
| **EC-05** | JPY amount `1500` | Accepted; minor unit 0, quantised to `1500`. |
| **EC-06** | Transaction submitted at 02:47 UTC via `api` | `unusual_timing` + `off_hours_api` both fire. |
| **EC-07** | `source_account == destination_account` | Rejected — `same_source_and_destination`. |
| **EC-08** | Message arriving at an agent with no `fraud` section | Held — `missing_fraud_assessment`. |
| **EC-09** | Empty `sample-transactions.json` (`[]`) | Pipeline exits `0`, summary reports 0 transactions, no crash. |
| **EC-10** | Malformed JSON in an inbox file | The file is quarantined with an audit entry; the run continues for the rest. |
| **EC-11** | Friday wire transfer | Value date rolls to the following Tuesday, not Sunday. |
| **EC-12** | Duplicate `transaction_id` in the input | Both are processed; result filenames are keyed by `message_id`, so neither overwrites the other. |
| **EC-13** | Fee below the floor (amount 100.00) | Fee is `0.50`, not `0.25`. |
| **EC-14** | Fee above the cap (amount 75 000) | Fee is `25.00`. |
| **EC-15** | `get_transaction_status` for an unknown id | `{"found": false, ...}` — a readable answer, not a traceback. |

---

## 8. Expected outcome for the supplied sample data

This table is the specification's own regression expectation and is asserted in
`tests/test_integration.py`.

| Transaction | Amount | Validator | Risk score | Compliance | Terminal status |
|---|---|---|---|---|---|
| TXN001 | 1 500.00 USD | validated | 0 (low) | cleared | **settled** |
| TXN002 | 25 000.00 USD | validated | 40 (medium), review required | cleared, CTR required | **settled** |
| TXN003 | 9 999.99 USD | validated | 35 (medium), structuring | cleared | **settled** |
| TXN004 | 500.00 EUR | validated | 40 (medium), unusual timing + off-hours API | cleared | **settled** |
| TXN005 | 75 000.00 USD | validated | 60 (high), review required | held | **held** |
| TXN006 | 200.00 XYZ | **rejected** — `unknown_currency:XYZ` | — | — | **rejected** |
| TXN007 | −100.00 GBP | **rejected** — `non_positive_amount` | — | — | **rejected** |
| TXN008 | 3 200.00 USD | validated | 0 (low) | cleared | **settled** |

Totals: **8 processed · 2 rejected · 1 held · 5 settled.**

---

## 9. Definition of done

- [ ] All nine Low-Level Tasks implemented, every acceptance checkbox verified with real output.
- [ ] `python integrator.py` exits 0; `shared/results/` holds one file per input record.
- [ ] `pytest --cov` ≥ 90 %; `scripts/coverage_gate.py` exits 0.
- [ ] Both MCP servers respond; the custom server's two tools and one resource return live data.
- [ ] `README.md` carries the author name, the ASCII diagram and the tech-stack table.
- [ ] `research-notes.md` documents the context7 queries actually made.
- [ ] Screenshots for spec, pipeline run, coverage, skill, hook and MCP saved under `docs/screenshots/`.
