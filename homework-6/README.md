# Homework 6 — AI-Powered Multi-Agent Banking Pipeline

> **Created by Simon Darienko** · team **Quorum** · Final capstone
> **AI tooling**: Claude Code (Opus 5) · MCP: `context7` + a custom FastMCP server
> **Run instructions**: [HOWTORUN.md](HOWTORUN.md) · **Spec**: [specification.md](specification.md) ·
> **Agent rules**: [agents.md](agents.md) · **Research**: [research-notes.md](research-notes.md)

---

## What this is

This project has two layers, and the assignment asks for both. The **outer layer** is four
*meta-agents* — AI workflows that build software: one writes the specification, one generates the
pipeline code, one writes the unit tests and enforces a coverage gate, and one produces the
documentation. The **inner layer** is what they built: a **multi-agent banking transaction
pipeline** that ingests raw transaction records and drives each one to an auditable terminal
outcome.

The pipeline itself is **six cooperating agents**. They started out communicating the way batch banking
systems do — by writing JSON message files into shared directories — and after
[CR-02](docs/change-requests/CR-02-agents-as-microservices.md) each agent also runs as **its own HTTP
service that calls its successor over REST**, with the files kept as the append-only journal. Both
transports drive the same decision functions, and a test asserts they never disagree on a verdict. A
transaction enters as a record in `sample-transactions.json`, is claimed by the **validator**
(required fields, exact-decimal amount, ISO 4217 currency, account format), scored by the **fraud
detector** (high value, structuring, unusual timing, cross-border, watchlist), screened by the
**compliance checker** (sanctions, CTR reporting duty, manual-review holds), routed by the
**policy engine** (business policy loaded from a JSON rule pack), booked by the **settlement
processor** (fee, net amount, business-day value date), and finally aggregated by the
**reporting agent**. Every hop appends to an append-only audit trail with an ISO 8601 timestamp,
and every account number is masked to `****NNNN` before it leaves the process. All money is
`decimal.Decimal` parsed from strings and rounded `ROUND_HALF_UP` — `float` never touches an
amount, a fee or a net figure. Once a run finishes, a custom **FastMCP server** makes the results
queryable by an LLM: two tools and one resource read the very files the pipeline wrote.

---

## The four meta-agents (the deliverable)

| Agent | Role | Its "plus" | Artefacts |
|---|---|---|---|
| **Agent 1 — Specification** | Writes the technical specification before any code exists | **Skill**: [`/write-spec`](.claude/commands/write-spec.md) renders the template on demand | [`specification.md`](specification.md), [`agents.md`](agents.md) |
| **Agent 2 — Code generation** | Implements the pipeline from the spec | **MCP context7**: 3 documented lookups (FastMCP API, CPython `decimal`, FastMCP transports) | [`integrator.py`](integrator.py), [`agents/`](agents), [`mcp/server.py`](mcp/server.py), [`research-notes.md`](research-notes.md) |
| **Agent 3 — Unit tests** | Writes the suite and enforces the floor | **Hook**: `PreToolUse` gate that **blocks `git push` below 80 %** coverage | [`tests/`](tests), [`scripts/coverage_gate.py`](scripts/coverage_gate.py), [`.claude/settings.json`](.claude/settings.json) |
| **Agent 4 — Documentation** | Produces the docs | **Requirement**: the README carries the author's name — *Simon Darienko* | `README.md`, [`HOWTORUN.md`](HOWTORUN.md) |

---

## The three interaction surfaces (CR-01, CR-02)

The engine above was extended twice, both times by written change requests rather than by conversation
— [`CR-01`](docs/change-requests/CR-01-interaction-interfaces.md) and
[`CR-02`](docs/change-requests/CR-02-agents-as-microservices.md).

| Surface | What it is | Entry point |
|---|---|---|
| **Rule packs** | Business policy as JSON. A sixth agent applies a pack; swapping packs changes outcomes with **zero code edits** — 5 settled/1 held becomes 3/3 and one fee moves. | [`rules/`](rules/) · [`rules/README.md`](rules/README.md) |
| **REST** | 16 routes in front of the pipeline, **and** the transport *between* agents: each agent is its own service and calls its successor over HTTP. Files stay as the journal. | `python -m services` · `python -m gateway --transport rest` |
| **One command** | `./demo.sh` — validation, both rule packs, the mesh, live HTTP submissions, tests, coverage gate, MCP. Zero manual steps, cleanup on failure and `Ctrl-C`. | [`demo.sh`](demo.sh) |
| **Presentation** | A self-contained HTML deck that **runs the demo from the page** and animates the real hops. Served by the gateway at `/`. | [`docs/presentation.html`](docs/presentation.html) |

```bash
./demo.sh --keep-running     # then open the printed gateway URL — the presentation is at /
```

## The six runtime agents (what they built)

- **`transaction_validator`** — claims raw records from `shared/input`. Checks that every required
  field is present, that the amount parses as an exact `Decimal`, is strictly positive and has no
  more decimals than the currency's minor unit, that the currency is a known ISO 4217 code, that
  the timestamp is ISO 8601, and that both accounts match `ACC-<4 digits>` and differ. Reports
  **every** failing check, not just the first. Masks the accounts and redacts the free-text
  description before anything else sees the record.
- **`fraud_detector`** — attaches a 0–100 risk score built from seven independent rules
  (`high_value`, `very_high_value`, `structuring`, `unusual_timing`, `cross_border`,
  `off_hours_api`, `watchlist_destination`), a risk level (`low` / `medium` / `high`) and the
  itemised list of what fired. Never modifies the amount; reads no wall clock — the transaction's
  own timestamp drives the timing rules.
- **`compliance_checker`** — decides `cleared` or `held`. Flags the CTR reporting duty at 10 000
  USD-equivalent, holds on sanctioned counterparty countries, on watchlisted destinations and on
  high-risk transactions awaiting manual review. **Fails closed**: a missing country, an
  unparseable amount or an absent fraud assessment is a hold, never a clearance.
- **`settlement_processor`** — books the cleared transaction: a 25 bp fee floored at 0.50 and
  capped at 25.00, the net amount, and a value date at T+1 (T+2 for wires) skipping weekends. The
  ledger invariant `fee + net_amount == amount` is asserted in code.
- **`policy_engine`** *(CR-01)* — applies a **rule pack loaded from JSON**: priority, SLA, tags, dual
  approval, and optional fee/lag overrides. Nothing it decides is hardcoded; a pack that will not load
  is a hold, never a silent approval. Every field it sets records `decided_by` naming the exact rule.
- **`reporting_agent`** — reads every terminal result and writes `shared/reports/`
  `pipeline-summary.json` and `pipeline-summary.md`: counts per status and risk level, volume per
  currency (never summed across currencies), and the reason list for everything that did not settle.

---

## Architecture

```
                       sample-transactions.json
                                  │
                                  ▼
                        ┌───────────────────┐
                        │    integrator     │  builds one protocol message per record
                        └─────────┬─────────┘
                                  │ writes
                                  ▼
   ┌─────────────────────── shared/input/ ────────────────────────┐
   │                                                              │
   │   ┌──────────────────────────┐                               │
   └──►│  transaction_validator   │──── invalid ─────────────┐    │
       │  fields · amount · ISO   │                          │    │
       │  4217 · account format   │                          │    │
       └────────────┬─────────────┘                          │    │
                    │ valid  →  shared/output/                │    │
                    ▼                                        │    │
       ┌──────────────────────────┐                          │    │
       │      fraud_detector      │                          │    │
       │  7 rules → score 0-100   │                          │    │
       │  low / medium / high     │                          │    │
       └────────────┬─────────────┘                          │    │
                    │ scored  →  shared/output/               │    │
                    ▼                                        │    │
       ┌──────────────────────────┐                          │    │
       │    compliance_checker    │──── held ────────────────┤    │
       │  sanctions · CTR ·       │                          │    │
       │  watchlist · fail closed │                          │    │
       └────────────┬─────────────┘                          │    │
                    │ cleared  →  shared/output/              │    │
                    ▼                                        │    │
       ┌──────────────────────────┐                          │    │
       │   settlement_processor   │──── settled ─────────────┤    │
       │  fee · net · value date  │                          │    │
       └──────────────────────────┘                          │    │
                                                             ▼    │
                                                  shared/results/ │
                                                             │    │
                                                             ▼    │
                                              ┌──────────────────┐│
                                              │  reporting_agent ││
                                              │  summary.json/md ││
                                              └────────┬─────────┘│
                                                       │          │
                                             shared/reports/ ◄────┘
                                                       │
                                                       ▼
                                         ┌──────────────────────────┐
                                         │  MCP  "pipeline-status"  │
                                         │  get_transaction_status  │
                                         │  list_pipeline_results   │
                                         │  pipeline://summary      │
                                         └──────────────────────────┘

   every hop also appends to  shared/audit/audit-log.jsonl
   (ISO 8601 timestamp · agent · transaction id · outcome, accounts masked ****NNNN)
   unreadable messages are moved to  shared/quarantine/  and the run continues
```

Since CR-02 the same chain also runs as five processes talking HTTP — `validator → fraud → compliance
→ policy → settlement` — where each service `POST`s to the next and the terminal verdict unwinds back
to the caller. The dashed journal lines above are unchanged: that is what "files under the hood for
logging" means.

Message format on the wire (one JSON file, or one HTTP body, per message):

```json
{
  "message_id": "uuid4-string",
  "timestamp": "2026-03-16T10:00:00Z",
  "source_agent": "transaction_validator",
  "target_agent": "fraud_detector",
  "message_type": "transaction",
  "data": { "transaction_id": "TXN001", "amount": "1500.00", "currency": "USD", "status": "validated" }
}
```

---

## Results for the supplied sample data

`python integrator.py` over the eight records in `sample-transactions.json`:

| Transaction | Amount | Risk | Compliance | Terminal status | Why |
|---|---|---|---|---|---|
| TXN001 | 1 500.00 USD | 0 (low) | cleared | **settled** | ordinary domestic transfer, fee 3.75 |
| TXN002 | 25 000.00 USD | 40 (medium) | cleared, CTR required | **settled** | above the 10 000 reporting threshold |
| TXN003 | 9 999.99 USD | 35 (medium) | cleared | **settled** | `structuring` — just under the threshold |
| TXN004 | 500.00 EUR | 40 (medium) | cleared | **settled** | `unusual_timing` 02:47 UTC + `off_hours_api` |
| TXN005 | 75 000.00 USD | 60 (high) | **held** | **held** | `high_value` + `very_high_value` → manual review |
| TXN006 | 200.00 XYZ | — | — | **rejected** | `unknown_currency:XYZ` |
| TXN007 | −100.00 GBP | — | — | **rejected** | `non_positive_amount` |
| TXN008 | 3 200.00 USD | 0 (low) | cleared | **settled** | ordinary domestic transfer |

**8 processed · 5 settled · 1 held · 2 rejected · reconciled=yes.**
This table is asserted transaction-by-transaction in `tests/test_integration.py`, so it is a
regression test, not a claim.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.12+** (developed on 3.14) | full type annotations, `decimal` in the standard library |
| Pipeline runtime | **standard library only** — `decimal`, `pathlib`, `json`, `uuid`, `datetime`, `re`, `argparse` | the pipeline runs on a bare Python install; no dependency can silently change money handling |
| Money | **`decimal.Decimal`**, parsed from `str`, `ROUND_HALF_UP` | `float` and `Decimal(1.1)` are both bugs — see [research-notes.md](research-notes.md) query 2 |
| Inter-agent transport | **REST** between services *(CR-02)*, with `shared/` kept as the append-only journal | the services talk to each other; files still make a run auditable and replayable |
| Rule engine | **declarative JSON** — no `eval`, no `exec` | a pack that cannot be fully understood is rejected at load time, naming the rule and field |
| HTTP | **`http.server`** — standard library | 16 routes, RFC 9457 `problem+json` errors, and still no runtime dependency |
| Tests | **pytest 9** + **pytest-cov** | 442 tests, `tmp_path` isolation, ephemeral ports, no sleeps |
| Coverage gate | **`scripts/coverage_gate.py`** as a Claude Code `PreToolUse` hook + a git `pre-push` hook | blocks a push below 80 %; the suite currently sits at **93 %** |
| MCP (custom) | **FastMCP 3** — `mcp/server.py` | 2 tools + 1 resource over stdio; tested over the in-memory transport |
| MCP (docs) | **`@upstash/context7-mcp`** | library lookups during code generation, documented in `research-notes.md` |
| Slash commands | `.claude/commands/` — `/write-spec`, `/run-pipeline`, `/validate-transactions` | the workflow as first-class Claude Code commands |

---

## Repository layout

```
homework-6/
├── specification.md            Agent 1 — the full spec (objectives, guardrails, edge cases, T-0..T-9)
├── agents.md                   Agent 1 — how any AI agent must behave in this repo
├── research-notes.md           Agent 2 — the context7 lookups, with what each one changed
├── README.md                   Agent 4 — this file
├── HOWTORUN.md                 Agent 4 — numbered steps from clone to demo
├── integrator.py               orchestrator
├── agents/
│   ├── protocol.py             messages, money, PII masking, audit trail, workspace
│   ├── base.py                 the drain loop every agent shares
│   ├── transaction_validator.py
│   ├── fraud_detector.py
│   ├── compliance_checker.py
│   ├── settlement_processor.py
│   ├── reporting_agent.py
│   └── results_store.py        read-only view behind the MCP server
├── agents/rule_engine.py       declarative rule engine (no eval, load-time validation)
├── agents/policy_engine.py     the sixth agent — policy from JSON
├── rules/                      policy-default.json · policy-strict.json · README.md
├── gateway/                    REST gateway: server · errors (RFC 9457) · validation · services
├── services/                   one HTTP service per agent: topology · client · agent_service · launcher
├── demo.sh                     one command, zero manual steps
├── mcp/server.py               custom FastMCP server (2 tools, 1 resource)
├── mcp.json                    context7 + pipeline-status
├── tests/                      232 tests — unit per agent + end-to-end integration
├── scripts/
│   ├── coverage_gate.py        the 80 % gate (Claude Code hook + CLI)
│   ├── pre-push                git hook wrapper around the same gate
│   ├── pipeline_reminder.py    optional PostToolUse hook
│   ├── verify_mcp_server.py    drives the MCP server over real stdio
│   ├── capture_evidence.py     regenerates the rendered terminal captures
│   └── install_claude_integration.py   wires hooks/commands/MCP into the repo root (reversible)
├── .claude/
│   ├── commands/               /write-spec · /run-pipeline · /validate-transactions
│   └── settings.json           the coverage-gate hook
├── docs/
│   ├── presentation.html       interactive deck — runs the demo, animates the chain
│   ├── change-requests/        CR-01 and CR-02 — the inputs the code was built from
│   ├── errors.md               the error catalog
│   ├── screenshots/            session captures + evidence panels
│   └── sample-run/             a committed copy of one full run's output
└── shared/                     runtime workspace (git-ignored, recreated by every run)
```

Everything this homework produces is **inside `homework-6/`**. Claude Code loads hooks, slash
commands and MCP servers from the repository root, so one explicit, reversible command wires them
up when you want them:

```bash
cd homework-6 && .venv/bin/python scripts/install_claude_integration.py   # --status / --uninstall
```

---

## Guardrails this project holds itself to

1. `float` never touches money — amounts are strings on the wire, `Decimal` in memory.
2. No account number, holder name or customer description in plaintext in a log, a report, the
   console or an MCP response. `AuditLogger` **raises** rather than write one.
3. Fail closed — missing country, absent fraud assessment, unparseable amount → hold or reject.
4. An agent adds its own section to `data`; it never edits another agent's, and never edits the
   amount after validation.
5. Every transaction ends exactly once in `shared/results/` with a status from
   `{rejected, held, settled}`; the integrator reconciles the count and exits non-zero if it does not.
6. Decision functions are pure — no wall clock, no randomness, so every result is reproducible.
7. **The transport is not part of the decision** — a service imports its agent's decision function
   unchanged, and a test asserts the REST chain and the in-process chain never disagree on a verdict.
8. **No hop loses or duplicates a transaction** — every hop is idempotent on `message_id`; an
   unreachable successor is a loud retryable `503`, journalled, never a silent drop.

Full list with ids: [`specification.md` §6](specification.md) and [`agents.md` §3](agents.md).
