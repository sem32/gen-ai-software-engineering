# Multi-Agent Banking Transaction Pipeline — Specification

> **Version 2.0** · **Author / Student**: Simon Darienko · **Homework 6 (Capstone)**
> **Produced by**: Agent 1 (Specification) — the `/write-spec` slash command in
> [`.claude/commands/write-spec.md`](.claude/commands/write-spec.md)
> **Companion documents**: [`agents.md`](agents.md) (how agents must behave) ·
> [`research-notes.md`](research-notes.md) (context7 research) ·
> [`README.md`](README.md) · [`HOWTORUN.md`](HOWTORUN.md) ·
> [`CR-01`](docs/change-requests/CR-01-interaction-interfaces.md) (the requirements this version adds)
>
> Ingest the information from this file, implement the Low-Level Tasks, and generate the code
> that will satisfy the High- and Mid-Level Objectives.

**What changed in 2.0.** Version 1.0 specified the engine: five agents, a file message protocol,
`Decimal` money, masked PII, an audit trail and a closed set of terminal statuses.
[CR-01](docs/change-requests/CR-01-interaction-interfaces.md) **adds interaction surfaces, not engine
changes** — a configurable rule engine driven by a sixth agent, an HTTP gateway in front of the file
protocol, a one-command demo and an HTML presentation. Everything from v1.0 is preserved verbatim
below and stays asserted; the new material is additive and carries new ids (`MO-7…MO-10`,
`T-10…T-16`, `IN-8…IN-10`, `EC-16…EC-26`, §3.8–§3.10, §8b). Existing ids were **not** renumbered, so
the committed tests, evidence and screenshots that reference them stay valid.

**What CR-02 changed after that.** Mid-implementation the requester reversed CR-01's central
constraint: *"агенты становятся микросервисами … между собой сервисы должны общаться по REST API …
под капотом они могут использовать файлы для логирования"*. So the transport between agents became
HTTP and the files were demoted from message bus to **journal** (audit trail plus terminal results).
[CR-02](docs/change-requests/CR-02-agents-as-microservices.md) records that, **withdraws guardrail
IN-8**, and adds §3.11, `T-17…T-19`, `IN-11…IN-13` and `EC-27…EC-32`. The five agents' decision
functions are still untouched — the services import them.

---

## 0. Requirements intake and traceability

The coding agent is driven by a written requirements artefact, never by a conversation. CR-01 was
captured as [`docs/change-requests/CR-01-interaction-interfaces.md`](docs/change-requests/CR-01-interaction-interfaces.md)
*before* any of the code it describes existed. This section is the chain from that request to the
tests that prove it.

| Rubric category | Weight | Requirement | Objective | Low-Level Task | Proof |
|---|---:|---|---|---|---|
| **Baseline** | 30 | v1.0 (unchanged) | MO-1 … MO-6 | T-0 … T-9 | §8 outcome table, asserted per transaction in `tests/test_integration.py`; the entire v1.0 suite still green |
| **New agent** | 25 | CR-01.1 | **MO-7** | **T-10, T-11, T-12** | `tests/test_rule_engine.py`, `tests/test_policy_engine.py`, the §8b strict-profile table |
| **API gateway** | 25 | CR-01.2 | **MO-8** | **T-13** | `tests/test_api_gateway.py` — every endpoint and every error path, over a real socket |
| **Quality** | 10 | CR-01.1–.3 | MO-7 … MO-9 | **T-16** | coverage gate ≥ 80 % enforced on push, suite ≥ 90 %; no `eval`; typed errors; documented rule schema |
| **Demo** | 10 | CR-01.3 | **MO-9** | **T-14** | `demo.sh` exit code plus its committed transcript |
| **AI best practice** | 10 | CR-01 process clause | **MO-10** | **T-15** | this section, CR-01, `research-notes.md`, the skills/hooks/MCP, screenshot provenance |
| **New agent / API gateway** | — | CR-02.1–.3 | **MO-11** | **T-17, T-18, T-19** | `tests/test_services.py` — §8 reproduced over REST hop by hop, idempotency, a downed successor |

**The invariant that governs 2.0**: *the base implementation does not change; the interaction
interface does.* Concretely — no decision function of the five original agents is edited, the message
contract is untouched, and a default run still produces the §8 baseline. Two existing tests that
assert pipeline *shape* (the claimed-message count and the set of agents in the audit trail) are
updated, because a sixth agent necessarily changes both. No test of a monetary value, a rejection
code, a risk score, a compliance decision or a masking rule changes.

---

## 1. High-Level Objective

Build a file-based multi-agent pipeline that ingests raw banking transactions from
`sample-transactions.json`, passes them through validation, fraud scoring, compliance screening,
**configurable business policy** and settlement as JSON messages on disk, and produces an auditable
per-transaction outcome in `shared/results/` plus a run summary report — reachable through three
interaction surfaces (**rule packs**, **HTTP**, **one-command demo**) that leave the engine untouched.

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

Added by CR-01. These four are the whole of version 2.0.

| id | Objective |
|---|---|
| **MO-7** | Business policy is **data, not code**. A sixth agent applies a rule pack loaded from JSON; changing which pack is active changes the pipeline's behaviour with **zero code edits**, and the effect is visible in the terminal results. A malformed pack fails at load time naming the offending rule and field. Rule-driven monetary overrides go through `Decimal` + `ROUND_HALF_UP` like every other money path. |
| **MO-8** | The same pipeline is reachable over HTTP: a transaction can be submitted and its terminal outcome retrieved through an API, with correct status codes, stable JSON error codes and **no new runtime dependency**. Responses are built only from the masked artefacts the pipeline wrote, so the HTTP surface cannot leak an account identifier the file surface would not. |
| **MO-9** | `./demo.sh` tells the whole story from a clean checkout with **zero manual steps**: validation, a default run, the same input under a stricter policy pack with the differences called out, live HTTP submissions, the test suite with its coverage gate, and the MCP server — always cleaning up what it started, and exiting non-zero if any step fails. |
| **MO-10** | The build is traceable as an AI-assisted process: every requirement exists as a written artefact before its code, `§0` maps requirement → objective → task → proof, and each generated surface names the evidence that verifies it. |

Added by CR-02.

| id | Objective |
|---|---|
| **MO-11** | Each agent runs as an **independent HTTP service**, and the services hand work to each other over REST rather than through a shared directory — while the file journal keeps the audit trail and the terminal results. A hop is idempotent on `message_id`, a downed successor is a loud retryable failure rather than a lost transaction, and the REST chain reproduces the §8 and §8b tables exactly, transaction by transaction, so the transport is provably not part of the decision. |

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

### 3.8 Rule-pack format (CR-01.1)

A pack is one JSON file. This is the entire contract; anything not listed here is a load error.

```json
{
  "name": "policy-default",
  "version": "1.0",
  "description": "Additive routing policy — never changes a monetary figure.",
  "defaults": { "priority": "standard", "sla_hours": 24 },
  "rules": [
    {
      "id": "express_small_low_risk",
      "description": "Small, low-risk, domestic — put it in the fast lane.",
      "enabled": true,
      "order": 10,
      "when": { "all": [
        { "fact": "usd_amount", "op": "<",  "value": "1000" },
        { "fact": "risk_level", "op": "==", "value": "low" }
      ]},
      "then": { "set": { "priority": "express", "sla_hours": 4 }, "tags": ["fast-lane"] },
      "stop": false
    }
  ]
}
```

**Conditions** are structured data — never source code. Four forms, freely nested:

| Form | Meaning |
|---|---|
| `{"all": [c, …]}` | every child is true (empty list ⇒ true) |
| `{"any": [c, …]}` | at least one child is true (empty list ⇒ false) |
| `{"not": c}` | the child is false |
| `{"fact": f, "op": o, "value": v}` | leaf comparison |

**Operators**: `==` `!=` `>` `>=` `<` `<=` `in` `not_in` `contains` `not_contains` `startswith`
`matches` (full-match regex) `is_true` `is_false` `exists` `missing`. Numeric operators compare as
`Decimal` when both sides parse as one, so `"usd_amount" >= "10000"` is exact, not float-ish. An
unknown operator, an unknown action key or a malformed leaf is a **load-time** `RuleError` naming the
pack, the rule id and the field.

**Actions** (`then`), all optional:

| Key | Effect |
|---|---|
| `set` | assigns scalar outcome fields: `priority`, `sla_hours`, `dual_approval_required`, `fee_rate`, `fee_floor`, `fee_cap`, `settlement_lag` |
| `tags` | appended to the outcome's tag list, de-duplicated, order preserved |
| `hold` | a stable reason code; sets `hold = true` and appends the code to `hold_reasons` |

**Evaluation order** is deterministic: rules sort by `order` (default `100`), ties broken by
declaration order. A matching rule with `"stop": true` ends evaluation. For scalar fields the last
writer wins, and the outcome records `decided_by[field] = rule_id` so a conflict is always
attributable. Disabled rules (`"enabled": false`) are skipped but still validated.

**Facts** available to a rule — a flat dictionary derived from the accumulated message payload:
`transaction_id`, `transaction_type`, `currency`, `amount`, `usd_amount`, `channel`, `country`,
`hour_utc`, `weekday`, `source_account`, `destination_account` (both masked), `status`, `risk_score`,
`risk_level`, `review_required`, `fraud_rules` (list of fired rule codes), `ctr_required`,
`compliance_decision`, `compliance_holds`, `is_cross_border`.

**Two packs ship.** `rules/policy-default.json` is additive — it sets priority, SLA, tags and
approval flags and touches no monetary field, so a default run reproduces §8 exactly.
`rules/policy-strict.json` holds on structuring and off-hours automation and applies a high-value fee
surcharge, producing §8b. Selecting a pack is configuration, never a code change: `--rules` on the
CLI, `HW6_POLICY_RULES` in the environment, `?rules=` on the API.

### 3.9 HTTP contract (CR-01.2)

Standard library only (`http.server.ThreadingHTTPServer`) — the "runs on a bare Python install"
property survives. The gateway owns no decision logic: it seeds a message and drains the same agents
in the same order, then reads the same artefacts the CLI reads.

| Method | Path | Purpose | Success |
|---|---|---|---|
| `GET` | `/health` | liveness plus workspace, active pack, uptime, result count | `200` |
| `GET` | `/rules` | the active rule pack as loaded | `200` |
| `POST` | `/transactions` | submit one transaction, run it, return its terminal outcome | `201` + `Location` |
| `POST` | `/transactions/batch` | submit an array (or `{"transactions": [...]}`) | `201` |
| `GET` | `/transactions` | list every processed transaction with per-status counts | `200` |
| `GET` | `/transactions/{id}` | one terminal outcome | `200` / `404` |
| `POST` | `/pipeline/run` | run the bundled sample end to end, return the summary | `200` |
| `GET` | `/summary` | run summary, JSON | `200` |
| `GET` | `/summary.md` | run summary, `text/markdown` | `200` |
| `GET` | `/audit` | tail of the audit trail, `?limit=N` (default 50, max 500) | `200` |

Error rules, all returning `{"error": "<stable_code>", "message": "…", "request_id": "…"}`:
`400 invalid_json` / `invalid_body` / `invalid_query`, `404 not_found` / `transaction_not_found`,
`405 method_not_allowed` (with an `Allow` header), `413 payload_too_large` (bodies over 1 MiB),
`500 internal_error`. Every response carries `X-Request-Id`, and that same id appears in the audit
trail entries the request produced, so an HTTP call can be traced to the file protocol.

Concurrency: `ThreadingHTTPServer` serves requests in parallel, but a pipeline drain claims files on
disk, so drains are serialised behind a single lock. Reads are not locked.

`?rules=<name>` on the two `POST` endpoints overrides the pack for that request only.

### 3.10 Demo contract (CR-01.3)

`./demo.sh` is the operator surface. It must be safe to run twice, on a clean checkout, offline if a
virtualenv already exists.

- Provisions `.venv` when absent; falls back to `python3` if provisioning is impossible, and says so.
- Steps, in order: validation dry-run → default-pack run → strict-pack run with a printed diff of the
  outcomes → gateway started on a **free** port, transactions submitted and results fetched over HTTP
  → `pytest` and the coverage gate → the MCP server.
- Readiness is **polled** (`/health`), never slept on blindly, with a bounded timeout.
- A `trap` stops the gateway on success, on failure and on `Ctrl-C`; the chosen port is released.
- Exits non-zero on the first failing step, and prints a per-step pass/fail summary at the end.
- Writes a transcript to `docs/sample-run/demo.log` so the run is reviewable afterwards.
- Flags: `--no-tests` (skip the slow step), `--port N` (pin the port), `--keep-running` (leave the
  gateway up for manual poking).

### 3.11 Service transport (CR-02)

Six services, one per agent, each started with `--agent <name> --port <n>`; the successor's URL is
configuration, never a constant inside an agent. `services/topology.py` derives the chain from
`PIPELINE_AGENTS`, so REST order cannot drift from in-process order.

**Choreography, not orchestration.** A service calls its own successor's `POST /process`. The chain is
*synchronous*: each service returns whatever came back from downstream, so the terminal verdict unwinds
to the original caller and one `POST` still answers with the final outcome. Rejected alternatives: a
broker (a new runtime dependency), and fire-and-forget with polling (the caller loses the verdict).

| Concern | Decision |
|---|---|
| Transport | `urllib.request` — the zero-dependency property survives |
| Timeout | per hop, 10 s default; the outermost caller must exceed the sum of the inner ones |
| Retries | bounded with exponential backoff, and **only** for transport faults. A downstream 4xx is an *answer* — retrying it would multiply load for no possible change |
| Idempotency | keyed on `message_id` **and** the active rule pack, persisted under `shared/processed/<agent>/`. A replay returns the first answer with `idempotent_replay: true` and writes no second result |
| Journal | every hop appends to `shared/audit/audit-log.jsonl` with the agent, transaction id, outcome, hop number and request id — a chain is reconstructable from files alone |
| Terminal write | the last service writes exactly one result file, so IN-5 survives the transport change |
| Per-request policy | `X-Policy-Rules` travels hop to hop, because the pack lives in a long-running service |
| Unreachable successor | `503 upstream_unavailable`, flagged `retryable` — safe precisely because hops are idempotent |
| Ports | a contiguous block from a base port, checked for availability before starting, with the base overridable via `HW6_SERVICE_BASE_PORT` |
| Auth | none. Loopback only, no credentials, stated as an explicit non-goal |

**Two transports, deliberately.** `--transport inprocess` drains the agents in one process — the batch
CLI and the whole pre-CR-02 test suite; `--transport rest` hands off to the mesh. Both drive the same
decision functions, and `test_rest_and_inprocess_transports_agree` asserts they never disagree.

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

Added by CR-01:

- `agents/rule_engine.py` — the declarative engine; `agents/policy_engine.py` — the sixth agent.
- `rules/policy-default.json`, `rules/policy-strict.json` — the two shipped packs, plus
  `rules/README.md` documenting the schema for a policy author.
- `gateway/server.py` — the stdlib HTTP gateway; `gateway/__main__.py` — `python -m gateway`.
- `demo.sh` — one command, zero manual steps; `docs/sample-run/demo.log` — its transcript.
- `docs/presentation.html` — the self-contained HTML presentation.
- `docs/change-requests/CR-01-interaction-interfaces.md` — the requirements artefact this version
  implements.
- `tests/test_rule_engine.py`, `tests/test_policy_engine.py`, `tests/test_api_gateway.py`.

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

### T-10. Declarative rule engine

**Task:** Configurable rule engine (CR-01.1) · **Serves:** MO-7

**Prompt:**
> "Create a standalone declarative rule engine for a regulated pipeline. Rules come from JSON, never
> from code: no `eval`, no `exec`, no importing a module named in config. Support the condition forms
> `all` / `any` / `not` and a `{fact, op, value}` leaf, with an explicit operator table covering the
> comparisons, membership, string and existence checks listed in spec §3.8; compare numerically as
> `Decimal` when both operands parse as one. Validate the whole pack at load time and raise a
> `RuleError` naming the pack, the rule id and the offending field — never fail at decision time and
> never skip a rule you could not understand. Evaluate in `order` then declaration order, let a rule
> stop evaluation, accumulate tags and hold reasons, and record which rule last set each scalar field."

**File to CREATE:** `agents/rule_engine.py`
**Functions/classes to CREATE:** `class RuleError`, `class Rule`, `class RulePack` with
`from_dict()` / `load()`, `evaluate_condition(condition, facts) -> bool`,
`apply_pack(pack, facts) -> dict`

**Details:**
- `RulePack.load(path)` reads, parses and validates in one step; a missing file raises `RuleError`,
  not `FileNotFoundError` leaking a path into an API response.
- The operator table is a module constant so a test can assert its exact key set.
- `apply_pack` returns `{"pack": {...}, "outcome": {...}, "matched_rules": [...],
  "decided_by": {...}, "evaluated": n}` and is **pure** — same pack + same facts ⇒ same dict.
- Monetary actions stay strings in the outcome; only the settlement processor turns them into
  `Decimal`, so the engine can never introduce a `float`.

**Acceptance criteria:**
- [ ] `grep -rn "eval(\|exec(" agents/rule_engine.py` finds nothing.
- [ ] Nested `all`/`any`/`not` evaluates correctly, and `all: []` is true while `any: []` is false.
- [ ] `{"fact":"usd_amount","op":">=","value":"10000"}` is exact for `"9999.99"` and `"10000.00"`.
- [ ] An unknown operator, an unknown action key, a missing `id`, a duplicate `id` and a non-object
      rule each raise `RuleError` mentioning the rule id or index.
- [ ] Two rules writing the same field resolve by `order`, and `decided_by` names the winner.
- [ ] `"stop": true` prevents later rules from firing.
- [ ] `apply_pack` called twice on the same input returns equal dicts.

---

### T-11. Policy engine agent

**Task:** The sixth agent (CR-01.1) · **Serves:** MO-7

**Prompt:**
> "Implement the `policy_engine` agent. It consumes compliance-cleared messages, builds the flat fact
> dictionary described in spec §3.8 from the accumulated payload, applies the active rule pack and
> attaches a `policy` section: `pack`, `priority`, `sla_hours`, `tags`, `dual_approval_required`, the
> optional `fee_rate` / `fee_floor` / `fee_cap` / `settlement_lag` overrides, `matched_rules` and
> `decided_by`. If the pack places a hold, the message is terminal with status `held` and the hold
> reasons; otherwise it is forwarded to `settlement_processor` with status `policy_cleared`. Fail
> closed: if the pack cannot be loaded or the facts cannot be built, hold. The pack is chosen by
> constructor argument, then `HW6_POLICY_RULES`, then the default pack — never hardcoded."

**File to CREATE:** `agents/policy_engine.py`
**Functions/classes to CREATE:** `class PolicyEngine(BaseAgent)` with
`build_facts(transaction) -> dict`, `apply(transaction) -> dict`, `process_message(message) -> dict`;
module-level `resolve_pack(spec=None) -> RulePack`, `DEFAULT_PACK_PATH`

**Details:**
- `build_facts` and `apply` are pure (guardrail IN-6) — no wall clock; `hour_utc` and `weekday` come
  from the transaction's own timestamp.
- The agent never edits `amount`, and never removes another agent's section (IN-4).
- `held` is already in the closed terminal set, so no new status is introduced (IN-5).

**Acceptance criteria:**
- [ ] With `policy-default`, all five settled sample transactions keep byte-identical `settlement`
      sections — the §8 table is unchanged.
- [ ] With `policy-strict`, TXN003 and TXN004 become `held`, and TXN002's fee becomes `87.50`.
- [ ] An unloadable pack produces `status == "held"` with `hold_reasons == ["policy_pack_unavailable"]`.
- [ ] `build_facts` on a fraud-scored, compliance-cleared payload exposes every fact named in §3.8.
- [ ] `HW6_POLICY_RULES` selects the pack when no constructor argument is given.

---

### T-12. Settlement honours policy overrides

**Task:** Wire the overrides (CR-01.1) · **Serves:** MO-7

**Prompt:**
> "Extend the settlement processor so it honours the optional `fee_rate`, `fee_floor`, `fee_cap` and
> `settlement_lag` overrides from the `policy` section. Absent overrides must reproduce today's
> behaviour exactly, so every existing settlement test keeps passing unchanged. Overrides are parsed
> from strings into `Decimal` and quantised `ROUND_HALF_UP` like every other money path, and the
> `fee + net_amount == amount` invariant still holds."

**File to UPDATE:** `agents/settlement_processor.py`
**Functions to UPDATE:** `calculate_fee(amount, currency, *, rate=None, floor=None, cap=None)`,
`settle_transaction(transaction)`

**Details:**
- The override source is recorded in the settlement section (`fee_source: "policy:<rule_id>"` or
  `"default"`) so a figure can always be explained.
- A negative or non-numeric override is a `MoneyError` — it does not fall back silently to the
  default.

**Acceptance criteria:**
- [ ] Every pre-existing settlement test passes with no edit.
- [ ] `fee_rate = "0.0035"`, `fee_cap = "100.00"` on 25 000.00 USD ⇒ fee `87.50`, net `24912.50`.
- [ ] `settlement_lag = 0` settles on the transaction date itself.
- [ ] `fee_rate = "-0.01"` raises `MoneyError`.
- [ ] `fee + net_amount == amount` for every override combination tested.

---

### T-13. REST API gateway

**Task:** HTTP surface (CR-01.2) · **Serves:** MO-8

**Prompt:**
> "Implement a REST gateway in front of the file-based pipeline using only the standard library
> (`http.server.ThreadingHTTPServer`). Implement exactly the routes, status codes and JSON error
> shape in spec §3.9. Submitting a transaction must run it through the real agents and return its
> terminal outcome — reimplement no decision. Serialise pipeline drains behind a lock because they
> claim files on disk. Assign a request id per request, return it as `X-Request-Id` and thread it into
> the audit trail. Cap bodies at 1 MiB. Build every response from the masked artefacts the pipeline
> wrote so a raw account identifier cannot appear in a response."

**Files to CREATE:** `gateway/server.py`, `gateway/__main__.py`
**Functions/classes to CREATE:** `class PipelineGateway` (routing + handlers),
`class GatewayHandler(BaseHTTPRequestHandler)`, `create_server(...) -> ThreadingHTTPServer`,
`main(argv=None) -> int`

**Details:**
- The router is a table of `(method, pattern) -> handler` so a test can enumerate the surface.
- `Content-Type: application/json` on every response except `/summary.md`.
- Logging goes to stderr in one line per request: method, path, status, duration, request id.
- `--host`, `--port` (`0` picks a free one and prints it), `--shared`, `--rules`, `--sample`.

**Acceptance criteria:**
- [ ] `GET /health` returns `200` with the active pack name and the workspace path.
- [ ] `POST /transactions` with a valid body returns `201`, a `Location` header and a terminal status.
- [ ] `POST /transactions` with an invalid transaction returns `201` and a **`rejected`** outcome —
      a business rejection is a successful API call, not a `400`.
- [ ] `POST /transactions` with malformed JSON returns `400 invalid_json`.
- [ ] `GET /transactions/NOPE` returns `404 transaction_not_found`.
- [ ] `DELETE /transactions` returns `405` with an `Allow` header.
- [ ] `GET /nope` returns `404 not_found`.
- [ ] A 2 MiB body returns `413 payload_too_large`.
- [ ] `?rules=policy-strict` on a submission changes that submission's outcome only.
- [ ] No response body in the whole test suite contains `ACC-`.
- [ ] Ten concurrent submissions all reach a terminal state exactly once.

---

### T-14. Demo script

**Task:** Operator surface (CR-01.3) · **Serves:** MO-9

**Prompt:**
> "Write `demo.sh`: one command, zero manual steps, implementing the contract in spec §3.10.
> Provision the virtualenv if needed, run the validation dry-run, a default-pack pipeline run, a
> strict-pack run with a printed diff of the outcomes, start the gateway on a free port, poll
> `/health` until ready, submit transactions and fetch results over HTTP, run the tests and the
> coverage gate, exercise the MCP server, then stop everything through a `trap` that also fires on
> failure and `Ctrl-C`. Print a per-step pass/fail summary, exit non-zero on the first failure, and
> tee a transcript to `docs/sample-run/demo.log`."

**File to CREATE:** `demo.sh` (executable)

**Acceptance criteria:**
- [ ] `./demo.sh` on a clean checkout exits `0` with no interactive prompt.
- [ ] Running it twice in a row succeeds both times.
- [ ] The gateway process is gone afterwards, and the port is free.
- [ ] Killing it mid-run with `Ctrl-C` leaves no orphan process.
- [ ] A forced failure in any step makes the script exit non-zero and say which step failed.
- [ ] `docs/sample-run/demo.log` exists afterwards and contains all steps.

---

### T-15. HTML presentation

**Task:** Explanatory surface (CR-01.4) · **Serves:** MO-10

**Prompt:**
> "Produce a self-contained HTML presentation of the project: the problem, the architecture of the six
> agents and the file protocol, the three new interaction surfaces, the rule-pack model with the
> default-versus-strict comparison, the API surface, the verification numbers, and the AI workflow
> that built it. One file, no external requests, readable in light and dark, keyboard-navigable."

**File to CREATE:** `docs/presentation.html`

**Acceptance criteria:**
- [ ] Opens from `file://` with no network access and renders fully.
- [ ] Contains the architecture diagram, both outcome tables, the endpoint list and the coverage number.
- [ ] Legible in light and dark themes.

---

### T-16. Tests for the new surfaces

**Task:** Quality (CR-01.1–.3) · **Serves:** MO-7, MO-8, MO-9

**Prompt:**
> "Cover the rule engine (every operator, every validation failure, ordering and conflict
> attribution), the policy engine (both packs, the fail-closed path, fact building), the settlement
> overrides, and every gateway route and error path over a real socket on an ephemeral port. Update
> only the two existing tests that assert pipeline shape. Keep total coverage above the 80 % gate and
> at or above the 90 % target."

**Files to CREATE:** `tests/test_rule_engine.py`, `tests/test_policy_engine.py`,
`tests/test_api_gateway.py`
**Files to UPDATE:** `tests/test_integration.py` (shape assertions only),
`tests/test_settlement_processor.py` (add override cases)

**Acceptance criteria:**
- [ ] `pytest` is green and total coverage is ≥ 90 %.
- [ ] The §8 table is still asserted transaction by transaction, and §8b is asserted too.
- [ ] Gateway tests bind port `0`, so they never collide with a running demo.
- [ ] No test writes into the repository's real `shared/`.

---

### T-17. Agents as services

**Task:** One process per agent (CR-02.1) · **Serves:** MO-11

**Prompt:**
> "Wrap each pipeline agent in its own HTTP service exposing `GET /health` and `POST /process`. Import
> the existing agent class — reimplement no decision. Derive the topology from `PIPELINE_AGENTS` so the
> REST order matches the in-process order, and tell each service its own name, port and successor URL
> through configuration. Make the hop idempotent on `message_id` plus the active rule pack, persisted
> so a restart does not forget. Keep writing the file journal: an audit line per hop, and the terminal
> result written by the last service."

**Files to CREATE:** `services/topology.py`, `services/agent_service.py`, `services/launcher.py`,
`services/__main__.py`

**Acceptance criteria:**
- [ ] `python -m services` starts one process per agent and reports the chain.
- [ ] `GET /health` names the agent, its successor and its rule pack.
- [ ] A message addressed to the wrong service is `400`, naming who it was addressed to.
- [ ] Replaying a `message_id` returns the first answer with `idempotent_replay: true` and writes no
      second result file.
- [ ] Starting on an occupied port fails immediately, naming the port.

---

### T-18. REST between services

**Task:** The wire (CR-02.2) · **Serves:** MO-11

**Prompt:**
> "Write the service-to-service client with the standard library: per-hop timeout, bounded retries with
> backoff, and a hard distinction between a downstream 4xx (a verdict — propagate, never retry) and a
> transport fault (retry, then raise). Have each service forward its emitted message to its successor
> and return what comes back, so the verdict unwinds to the original caller. Forward `X-Request-Id` and
> `X-Policy-Rules` along the chain."

**Files to CREATE:** `services/client.py`
**Functions to CREATE:** `post_json`, `get_json`, `wait_until_healthy`, `class TransportError`

**Acceptance criteria:**
- [ ] The REST chain reproduces §8 exactly: 5 settled, 1 held, 2 rejected.
- [ ] The strict pack over REST reproduces §8b.
- [ ] The trace returned to the caller lists the hops first-to-last with each status.
- [ ] A rejected transaction never reaches the second service.
- [ ] Killing a mid-chain service yields `503 upstream_unavailable` with `retryable: true`, and the
      failure is in the journal as `forward_failed`.
- [ ] A 4xx from downstream is returned after exactly one attempt.

---

### T-19. Gateway over the mesh, and the interactive presentation

**Task:** One system, not two demos (CR-02.3, CR-01.4) · **Serves:** MO-8, MO-9, MO-11

**Prompt:**
> "Give the gateway a `--transport rest` mode that hands the transaction to the first agent service and
> relays the unwound verdict, keeping `inprocess` as the default so the batch CLI and the existing tests
> are untouched. Serve `docs/presentation.html` from the gateway root so the presentation is same-origin
> with the API and can drive it with no configuration; add permissive CORS so a `file://` copy works too.
> The presentation must visualise the chain hop by hop from the real `trace` in the response, and fall
> back to recorded responses when no API is reachable."

**Files to UPDATE:** `gateway/server.py` · **Files to CREATE:** `docs/presentation.html`

**Acceptance criteria:**
- [ ] `GET /` returns the presentation as `text/html`.
- [ ] `OPTIONS` answers a CORS preflight for a JSON POST.
- [ ] A submission in `rest` mode returns `transport: "rest"` and a five-hop trace.
- [ ] `?rules=policy-strict` changes that submission's verdict in `rest` mode too.
- [ ] The page shows `live` when served by the gateway and degrades to recorded data when not.

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
| **IN-8** | **The base implementation is frozen** (CR-01). No decision function of the five original agents is edited, the message contract is unchanged, and a default run still reproduces §8. New behaviour arrives as a new agent, a rule pack or a new surface — never as an edit to an existing decision. |
| **IN-9** | **Rules are data, never code.** No `eval`, no `exec`, no importing a module named in a config file. A pack that cannot be fully understood fails at load time; an unparseable pack is a hold, not a bypass. |
| **IN-8** | ~~The base implementation is frozen~~ — **withdrawn by CR-02.** Superseded by IN-11: the transport may change, the decisions may not. |
| **IN-11** | **The transport is not part of the decision.** A service imports its agent's decision function unchanged. Any transport must reproduce §8 and §8b exactly; a test asserts `inprocess` and `rest` agree. |
| **IN-12** | **No hop may lose or duplicate a transaction.** Every hop is idempotent on `message_id`; a retry returns the first answer. An unreachable successor is a loud retryable error, never a silent drop, and the failure is journalled. |
| **IN-13** | **The journal survives every refactor.** Whatever the transport, each hop appends to the audit trail and exactly one terminal result file is written. If a change would weaken that, the change is wrong. |
| **IN-10** | **A new surface may not widen the PII or trust surface.** Every HTTP response is built from artefacts the pipeline already masked; the gateway adds no field the file protocol does not have, and it never returns an internal exception message to a caller. |

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

Added by CR-01.

| id | Case | Required behaviour |
|---|---|---|
| **EC-16** | Rule pack file missing or unreadable | `RuleError` at load; the agent holds with `policy_pack_unavailable`. Never "no rules, so approve". |
| **EC-17** | Rule with an unknown operator or action key | `RuleError` at **load** time naming the rule id and the key. The pack is rejected whole — no partial application. |
| **EC-18** | Two rules set the same field | Resolved by `order` then declaration order; `decided_by[field]` names the winner. |
| **EC-19** | `{"all": []}` / `{"any": []}` | `all` of nothing is **true**; `any` of nothing is **false**. Both asserted, because guessing here silently inverts a policy. |
| **EC-20** | Rule sets `fee_rate` to a negative or non-numeric value | `MoneyError` — never a silent fall back to the default rate. |
| **EC-21** | `settlement_lag = 0` | Settles on the transaction date; the business-day walk still skips weekends for non-zero lags. |
| **EC-22** | `POST /transactions` with a business-invalid transaction | `201` with a `rejected` outcome. A rejection is a successful API call — `400` is reserved for a malformed *request*. |
| **EC-23** | `POST /transactions` with malformed JSON, or a 2 MiB body | `400 invalid_json` / `413 payload_too_large`; the connection is drained and the server stays up. |
| **EC-24** | Ten concurrent submissions | Each reaches a terminal state exactly once; drains are serialised, so no message is claimed twice and none is lost. |
| **EC-25** | `GET /transactions/{unknown}` and `DELETE /transactions` | `404 transaction_not_found` and `405` with an `Allow` header — not `500`. |
| **EC-26** | `demo.sh` interrupted with `Ctrl-C`, or a step fails | The `trap` stops the gateway either way; the script exits non-zero and names the failing step. No orphan process, no held port. |

Added by CR-02.

| id | Case | Required behaviour |
|---|---|---|
| **EC-27** | A service receives a message addressed to a different agent | `400 invalid_body`, naming who it was addressed to. Never processed "helpfully". |
| **EC-28** | The same `message_id` is POSTed twice to a service | The first answer is returned again with `idempotent_replay: true`; exactly one result file exists. |
| **EC-29** | A non-message body, or an empty payload, reaches `/process` | `400`/`422` with a problem document — a verdict or a schema error, never a `500`. |
| **EC-30** | The successor service is down | `503 upstream_unavailable`, `retryable: true`, the attempt count reported, `forward_failed` in the journal, and no internal URL in the response. |
| **EC-31** | A subprocess service computes a different topology than its parent | Impossible by construction: the base port is passed to every child. Found by `demo.sh` when it was *not* — only the first hop worked. |
| **EC-32** | One of the mesh's ports is already in use | The launcher refuses to start, naming the port and how many it needs, rather than leaving half a mesh running. |

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

This table is produced by a run under the **default** rule pack, and CR-01 does not change it — that
is the whole point of IN-8. The policy engine attaches routing metadata to these outcomes
(`priority`, `sla_hours`, `tags`, `dual_approval_required`) and changes no monetary figure.

## 8b. Expected outcome under `policy-strict` (CR-01.1)

The same eight inputs, the same code, a different rule pack. This is the demonstration that policy is
configuration; it is asserted in `tests/test_policy_engine.py` and printed side by side by `demo.sh`.

| Transaction | Amount | Fires | Policy outcome | Terminal status | Δ vs §8 |
|---|---|---|---|---|---|
| TXN001 | 1 500.00 USD | — | express, fee 3.75 | **settled** | — |
| TXN002 | 25 000.00 USD | `strict_high_value_surcharge` | fee rate 0.0035, cap 100.00 → **fee 87.50**, net 24 912.50 | **settled** | fee 25.00 → **87.50** |
| TXN003 | 9 999.99 USD | `strict_structuring_hold` | hold — `structuring_manual_review` | **held** | settled → **held** |
| TXN004 | 500.00 EUR | `strict_off_hours_hold` | hold — `off_hours_automation_review` | **held** | settled → **held** |
| TXN005 | 75 000.00 USD | — (held earlier by compliance) | never reaches policy | **held** | — |
| TXN006 | 200.00 XYZ | — (rejected by the validator) | never reaches policy | **rejected** | — |
| TXN007 | −100.00 GBP | — (rejected by the validator) | never reaches policy | **rejected** | — |
| TXN008 | 3 200.00 USD | — | standard, fee 8.00 | **settled** | — |

Totals: **8 processed · 2 rejected · 3 held · 3 settled** — versus 1 held / 5 settled by default.
Two extra holds and one changed fee, from editing JSON only.

---

## 9. Definition of done

- [ ] All nine Low-Level Tasks implemented, every acceptance checkbox verified with real output.
- [ ] `python integrator.py` exits 0; `shared/results/` holds one file per input record.
- [ ] `pytest --cov` ≥ 90 %; `scripts/coverage_gate.py` exits 0.
- [ ] Both MCP servers respond; the custom server's two tools and one resource return live data.
- [ ] `README.md` carries the author name, the ASCII diagram and the tech-stack table.
- [ ] `research-notes.md` documents the context7 queries actually made.
- [ ] Screenshots for spec, pipeline run, coverage, skill, hook and MCP saved under `docs/screenshots/`.

Added by CR-01 (version 2.0):

- [ ] T-10…T-16 implemented, every acceptance checkbox verified with real output.
- [ ] IN-8 holds: `git diff` shows no edit to a decision function of the five original agents, and the
      §8 table is still asserted and still passing.
- [ ] Both rule packs load; switching them changes the outcome with no code edit; §8b reproduced.
- [ ] Every route and every error path in §3.9 exercised against a real socket.
- [ ] `./demo.sh` exits 0 from a clean checkout with zero manual steps, and leaves no orphan process.
- [ ] `docs/presentation.html` opens offline and covers architecture, both packs, the API and the numbers.
- [ ] Coverage still ≥ 90 % with the 80 % push gate green.

Added by CR-02:

- [ ] T-17…T-19 implemented, every acceptance checkbox verified with real output.
- [ ] IN-11 holds: the REST chain and the in-process chain produce identical verdicts, asserted.
- [ ] Idempotency, timeouts, bounded retries and the `503` path all covered by tests.
- [ ] `python -m services` + `python -m gateway --transport rest` reproduce §8 over HTTP.
- [ ] The presentation is served at `GET /` and drives the live API from the page.
