# CR-01 — Interaction interfaces and a configurable rule engine

> **Status**: accepted · **Received**: 2026-08-12 · **Author of the request**: course instructor
> **Recipient**: Agent 2 (code generation) — this document is its *input*
> **Derived spec sections**: [`specification.md`](../../specification.md) §0, §2 (MO-7…MO-10),
> §3.8–§3.10, §5 (T-10…T-16), §6 (IN-8…IN-10), §7 (EC-16…EC-26), §8b
> **Scope constraint from the requester**: *"базовая имплементация не меняется, меняется сам
> интерфейс взаимодействия"* — the base implementation does not change; what changes is the
> interaction interface.

---

## 1. Requirements as received

Verbatim, three numbered requirements plus one deliverable:

> 1. A new agent + configurable rule engine
> 2. A REST API gateway — wrap your file-based pipeline behind HTTP endpoints so transactions can be
>    submitted and results retrieved via API calls.
> 3. A demo script — a single `demo.sh` that starts everything, submits test transactions, and
>    displays results with zero manual steps.
>
> кроме самого демо скрипта необходимо подготовить призентацию в виде html
> *(besides the demo script itself, an HTML presentation must be prepared)*

And a clarification of intent, received after the requirements:

> базовая имплементация не меняется, меняется сам интерфейс взаимодействия
> Агент, который пишет код должен на вход получить новые требования

The second line is a process requirement, not a product one: the coding agent must be driven by a
written requirements artefact. This document is that artefact, and it is the reason it exists before
any of the code it describes.

---

## 2. Interpretation

The pipeline built for the original assignment is the *engine*. CR-01 does not change the engine —
it adds **surfaces**: new ways for a human, a script, an HTTP client or a rule author to interact
with the same five agents.

| # | Requirement | What kind of surface | What must NOT change |
|---|---|---|---|
| 1 | New agent + configurable rule engine | **Behaviour surface** — policy expressed as data (rule packs) instead of code, applied by a sixth agent | The five existing agents' decision logic; the money, PII, audit and fail-closed guarantees |
| 2 | REST API gateway | **Network surface** — HTTP in front of the existing file protocol | The file protocol itself; results are still produced by the same agents in the same order |
| 3 | `demo.sh` | **Operator surface** — one command, zero manual steps | Nothing; it only orchestrates existing entry points |
| 4 | HTML presentation | **Explanatory surface** — the project explained to a reviewer | Nothing |

**Consequence for the regression baseline**: the §8 outcome table of the specification
(8 processed · 5 settled · 1 held · 2 rejected) **stays valid and stays asserted**. The default rule
pack is deliberately *additive* — it attaches priority, SLA, tags and approval flags, and does not
touch a single monetary figure. Behaviour changes are demonstrated with a **second** rule pack
(`strict`), which is exactly the point of making the engine configurable: the same code produces a
different, auditable outcome when the policy data changes.

Two existing tests assert pipeline *shape* rather than behaviour — the number of claimed messages
and the set of agents appearing in the audit trail. Inserting a sixth agent changes both by
construction, so those two assertions are updated. No test of a monetary value, a rejection code, a
risk score, a compliance decision or a masking rule changes.

---

## 3. Acceptance criteria

### CR-01.1 — New agent + configurable rule engine

- [ ] A new runtime agent joins the pipeline between compliance screening and settlement. It is the
      sixth agent and it obeys the same contract as the other five: drains an inbox, claims into
      `processing/`, emits exactly one outgoing message, audits before writing.
- [ ] Its entire behaviour comes from a **rule pack loaded from a JSON file** — no policy decision is
      hardcoded in the agent.
- [ ] The rule engine is a standalone, reusable module with **no `eval`, no `exec`, no imports from
      config**. Conditions are structured data (`all` / `any` / `not` / a fact-operator-value triple)
      evaluated by an explicit operator table.
- [ ] A malformed rule pack fails **loudly at load time** with the offending rule id and field —
      never silently at decision time, and never by ignoring the rule.
- [ ] Rules can: set a field, add tags, require dual approval, override the fee rate / floor / cap,
      override the settlement lag, and place a hold. A rule may stop further evaluation.
- [ ] Rule order is deterministic and documented (`priority`, then declaration order); the winning
      rule for any conflicting field is reported in the output.
- [ ] Two packs ship: `policy-default` (additive, preserves the §8 baseline) and `policy-strict`
      (holds on structuring and off-hours automation, applies a high-value fee surcharge).
- [ ] Switching packs requires **no code change** — a CLI flag, an env var and an API field select it.
- [ ] Monetary overrides still go through `Decimal` + `ROUND_HALF_UP`; a rule cannot introduce a
      `float` into a money path.
- [ ] Fail closed: an unknown pack path, an unreadable pack or a rule that cannot be evaluated
      results in a hold, never a silent approval.

### CR-01.2 — REST API gateway

- [ ] Transactions can be **submitted** over HTTP and results **retrieved** over HTTP.
- [ ] Endpoints: health, submit one, submit a batch, get one result, list results, run the bundled
      sample, run summary (JSON and Markdown), the active rule pack, and the audit tail.
- [ ] Submitting a transaction runs it through the real agents and returns its terminal outcome —
      the gateway does not reimplement any decision.
- [ ] **No new runtime dependency.** The gateway uses the standard library, so the "runs on a bare
      Python install" property of the project survives.
- [ ] Correct HTTP semantics: `200`/`201`/`202` on success, `400` on a malformed body, `404` on an
      unknown route or transaction id, `405` on a wrong method, `413` on an oversized body, `500`
      only for genuine internal faults. Every error is a JSON object with a stable `error` code.
- [ ] The gateway **never widens the PII surface**: every response is built from the same masked
      artefacts the pipeline wrote. A raw account identifier cannot appear in a response body.
- [ ] Concurrent requests cannot corrupt the file protocol — pipeline drains are serialised.
- [ ] A request id is assigned per request, logged, and returned in a response header so a call can
      be traced to its audit entries.

### CR-01.3 — `demo.sh`

- [ ] **One command, zero manual steps**: `./demo.sh` from a clean checkout produces the whole story.
- [ ] It provisions its own environment if needed, and degrades gracefully to the system interpreter.
- [ ] It exercises, in order: validation dry-run → pipeline run (default pack) → the same input under
      the strict pack, with the differences called out → REST gateway started, transactions submitted
      and results retrieved over HTTP → tests and the coverage gate → the MCP server.
- [ ] It picks a free port, waits for readiness rather than sleeping blindly, and **always** stops
      what it started, including on failure or `Ctrl-C`.
- [ ] It exits non-zero if any step fails, and prints a final pass/fail summary.
- [ ] It writes a transcript so the run can be reviewed after the fact.

### CR-01.4 — HTML presentation

- [ ] A self-contained HTML presentation explaining the problem, the architecture, the new
      interaction surfaces, the results and the AI workflow used to build it.
- [ ] Works offline from a single file, readable in both light and dark themes.
- [ ] Contains the architecture diagram, the outcome tables for both rule packs, the endpoint list
      and the verification numbers.

---

## 4. Mapping to the evaluation criteria

The request arrived alongside a scoring rubric with six weighted categories totalling **110**. This
mapping is what the specification's §0 traceability table is organised around.

| Category | Weight | Where CR-01 is answered |
|---|---:|---|
| **Baseline** | 30 | Unchanged and still asserted: 5 agents, file protocol, `Decimal` money, PII masking, audit trail, fail-closed, §8 outcome table, 232 existing tests |
| **New agent** | 25 | CR-01.1 — `policy_engine` + `rule_engine`, two shipped packs, load-time validation, deterministic ordering, `Decimal`-safe overrides |
| **API gateway** | 25 | CR-01.2 — stdlib HTTP gateway, full CRUD-ish surface over submissions and results, strict status codes, masked responses, serialised drains |
| **Quality** | 10 | New unit + integration tests for the engine, the agent and every endpoint; coverage floor held ≥ 80 % (gate) with the suite ≥ 90 %; no `eval`; typed errors; documented rule schema |
| **Demo** | 10 | CR-01.3 — `demo.sh`, zero manual steps, both rule packs, live HTTP calls, cleanup on failure, transcript |
| **AI best practice** | 10 | This document as the coding agent's input; spec-first flow with traceability `CR → MO → T → test`; skills, hooks, MCP and `research-notes.md`; explicit provenance for every screenshot |

---

## 5. Out of scope for CR-01

Stated so a reviewer does not have to guess whether something was forgotten:

- No authentication, TLS or rate limiting on the gateway — it is a local demo surface, and adding
  half of an auth story would be worse than none. Called out in the presentation and the README.
- No database. The file protocol *is* the storage model of this project.
- No async/queued submission. Submissions are processed synchronously so a caller gets the terminal
  outcome in the response; the pipeline is sub-millisecond per transaction at this scale.
- No change to the five existing agents' decision logic, to the message contract, or to the money,
  PII and audit guarantees.
