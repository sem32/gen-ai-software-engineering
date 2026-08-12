# CR-02 — Agents become microservices that talk over REST

> **Status**: accepted · **Received**: 2026-08-12 (during CR-01 implementation)
> **Recipient**: Agent 2 (code generation) — this document is its *input*
> **Supersedes**: guardrail **IN-8** of specification v2.0 ("the base implementation is frozen")
> **Derived spec sections**: §3.11, §5 (T-17…T-19), §6 (IN-11…IN-13), §7 (EC-27…EC-32)

---

## 1. Requirements as received

> агенты становятся микросервисами, которые процессят пайплайны, были файлы — стали REST API запросы
>
> между собой сервисы должны общаться по REST API
>
> при этом под капотом они могут использовать файлы для логирования

*(The agents become microservices that process pipelines; what were files are now REST API requests.
The services must talk to each other over REST. Under the hood they may still use files for logging.)*

---

## 2. What this changes, stated plainly

CR-01 was explicitly scoped as "the base implementation does not change; the interaction interface
does", and it was built that way: the five agents kept exchanging JSON files, and HTTP existed only at
the outer boundary. **CR-02 reverses that constraint.** The transport *between* agents becomes REST;
files stop being the transport and keep two narrower jobs.

| Concern | CR-01 (before) | CR-02 (after) |
|---|---|---|
| Transport between agents | JSON files in `shared/output`, claimed via `shared/processing` | **HTTP `POST /process`** from one agent service to the next |
| Process model | one process, five classes | **one process per agent**, independently startable and health-checkable |
| Who routes | each agent writes a file addressed to the next agent | each service **calls** its successor; the successor's URL is configuration |
| Audit trail | `shared/audit/audit-log.jsonl` | **unchanged** — still the append-only file journal |
| Terminal results | `shared/results/*.json` | **unchanged** — the last service in the chain writes the result file |
| Replay / inspection | read the files | read the same files |

So "files for logging" is honoured literally: `shared/audit/` and `shared/results/` remain
file-based, because that is what makes a run auditable and replayable. What disappears is
`shared/input` / `shared/processing` / `shared/output` as the *message bus*.

**IN-8 is withdrawn** and replaced by IN-11…IN-13 (below). The five agents' *decision functions* are
still untouched — `validate_transaction`, `score_transaction`, `screen_transaction`,
`settle_transaction` and the rule engine are imported by the services, not rewritten. What changes is
the plumbing around them.

---

## 3. Chosen architecture: synchronous choreography

Two shapes were on the table.

**Orchestration** — one coordinator calls each service in turn. Simple, but the services never talk to
each other, which is precisely what the requirement asks for.

**Choreography** — each service calls its own successor. This is what CR-02 says, so this is what is
built. The chain is *synchronous*: a service returns the outcome it received from downstream, so the
result unwinds back to the original caller and `POST /transactions` can still answer with the terminal
verdict in one request.

```
client ──POST /transactions──▶ gateway
                                  │  POST /process
                                  ▼
                        transaction_validator ──POST /process──▶ fraud_detector
                                  ▲                                   │
                                  │                                   ▼
                                  │                          compliance_checker
                                  │                                   │
                                  │                                   ▼
                                  │                            policy_engine
                                  │                                   │
                                  │                                   ▼
                                  └──── terminal outcome unwinds ── settlement_processor
                                                                      │
                                                                      ▼
                                                       shared/results/*.json   (file journal)
                                                       shared/audit/*.jsonl    (every hop)
```

Rejected alternatives and why: a message broker (out of scope, and a new runtime dependency); fire and
forget with polling (the caller would lose the synchronous verdict the current API contract gives);
each service owning its own database (the file journal already is the storage model of this project).

---

## 4. Acceptance criteria

### CR-02.1 — Each agent is an independent service

- [ ] One process per agent, started with `--agent <name> --port <n> --next <url>`; nothing about the
      topology is hardcoded in an agent.
- [ ] `GET /health` on each service reports its agent name, its successor and its uptime.
- [ ] `POST /process` accepts a protocol message, runs **the existing agent code**, and returns the
      terminal outcome from downstream.
- [ ] A service imports its agent's decision function unchanged — no logic is reimplemented.
- [ ] Services are startable in any order; a service whose successor is not yet up fails the call
      loudly rather than dropping the message.

### CR-02.2 — REST between services

- [ ] The forward hop is an HTTP call to the successor's `/process`, using the standard library only.
- [ ] Per-hop **timeout** and bounded **retries with backoff**; a hop that keeps failing surfaces as a
      typed error, never as a lost transaction.
- [ ] **Idempotency**: replaying the same `message_id` at a service does not double-process it or
      write a second result; the first outcome is returned again.
- [ ] Every hop appends to the shared audit journal with the agent, the transaction id, the outcome
      and the request id, so a chain can be reconstructed from files alone.
- [ ] The terminal service writes exactly one result file (guardrail IN-5 survives).
- [ ] A downstream 4xx (a business verdict) is distinguished from a downstream 5xx (a transport
      fault): the first propagates as a verdict, the second as a retryable failure.

### CR-02.3 — The pipeline still behaves identically

- [ ] The §8 outcome table is reproduced by the REST chain, transaction by transaction.
- [ ] The §8b strict-pack table is reproduced by the REST chain too.
- [ ] `demo.sh` starts every service, submits transactions over HTTP, shows the hop-by-hop trace, and
      stops every process it started — including on failure and `Ctrl-C`.
- [ ] The in-process path (`integrator.py`) keeps working for batch runs and for the existing test
      suite; the transport is a choice (`--transport rest|inprocess`), not a fork of the logic.

---

## 5. Consequences accepted deliberately

- **Latency and failure modes get real.** Five nested synchronous HTTP calls mean the outermost
  timeout must exceed the sum of the inner ones, and a mid-chain crash leaves a partially processed
  transaction. Mitigated by idempotency keys and the audit journal, not hidden.
- **The file journal is written by several processes.** Appends are line-sized and opened in append
  mode, which is atomic enough for a demo on one host; a real deployment would ship to a log service.
  Stated in the presentation rather than glossed over.
- **No auth between services.** They bind to loopback only. Called out in `docs/errors.md` and the
  README as an explicit non-goal for a local demo.
- **Two transports now exist.** That is a feature, not drift: `inprocess` keeps the 232 existing tests
  and the batch CLI honest, `rest` is the CR-02 architecture. Both drive the same decision functions,
  and a test asserts they produce identical outcomes.
