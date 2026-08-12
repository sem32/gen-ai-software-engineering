# Homework 6 (Capstone) — Multi-Agent Banking Pipeline

**Created by Simon Darienko** · team **Quorum** · branch `homework-6-submission` → `main`
Everything in this PR lives inside [`homework-6/`](homework-6/). Nothing outside that folder is touched.

---

## 1. What this is

A transaction enters as JSON and leaves with a defensible answer — **settled**, **held** or
**rejected** — with every hop journalled, every account masked, and every figure explainable down to
the rule that produced it.

The project was built in three passes, each driven by a **written requirements artefact rather than a
conversation**:

| Pass | Input document | What it added |
|---|---|---|
| Base | [`specification.md`](homework-6/specification.md) v1.0 | Five agents exchanging JSON files, `Decimal` money, masked PII, an audit trail, a closed status set, MCP, skills, a coverage-gate hook |
| **CR-01** | [`CR-01`](homework-6/docs/change-requests/CR-01-interaction-interfaces.md) | A sixth agent driven by a **configurable rule engine**, a **REST gateway**, `demo.sh`, an HTML presentation |
| **CR-02** | [`CR-02`](homework-6/docs/change-requests/CR-02-agents-as-microservices.md) | Agents became **microservices talking REST to each other**; files demoted from message bus to journal. Explicitly **withdrew** CR-01's "base implementation is frozen" guardrail |

`specification.md` §0 carries the traceability chain — requirement → objective → task → the test that
proves it — organised around the six scoring categories.

### The six agents

`transaction_validator` → `fraud_detector` → `compliance_checker` → **`policy_engine`** →
`settlement_processor`, with `reporting_agent` aggregating.

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
                                  └──── terminal verdict unwinds ── settlement_processor
                                                                      │
                                                                      ▼
                                                       shared/results/*.json   (file journal)
                                                       shared/audit/*.jsonl    (every hop)
```

---

## 2. CR-01 — a new agent whose behaviour is data

`agents/rule_engine.py` is a declarative engine: conditions are **structured data**
(`all` / `any` / `not` plus a `{fact, op, value}` leaf) evaluated by an explicit 16-operator table.
There is **no `eval`, no `exec`, no importing a module named in config** — a test greps the source to
keep it that way. A malformed pack is rejected at **load time**, naming the pack, the rule and the
field, so a typo can never silently disable a control at decision time.

`agents/policy_engine.py` is the sixth agent. It owns no policy: it loads a pack and applies it.

**The demonstration — same code, same input, different JSON:**

| Transaction | `policy-default` | `policy-strict` |
|---|---|---|
| TXN002 25 000.00 | settled, fee **25.00** | settled, fee **87.50** |
| TXN003 9 999.99 | settled | **held** — structuring |
| TXN004 500.00 EUR | settled | **held** — off-hours automation |
| totals | 5 settled · 1 held · 2 rejected | **3 settled · 3 held · 2 rejected** |

Both tables are asserted transaction by transaction (`specification.md` §8 and §8b). Selecting a pack
is configuration: `--rules`, `HW6_POLICY_RULES`, `?rules=` on the API, `X-Policy-Rules` between
services. Schema and semantics: [`rules/README.md`](homework-6/rules/README.md).

Deliberate sharp edges, all tested: a float operand is **refused** (`9.0 > "10"` is false numerically
and true lexicographically — guessing would invert a policy); `all` of nothing is true, `any` of
nothing is false; a disabled rule is still validated; an unloadable pack is a **hold**.

---

## 3. CR-02 — agents as microservices, REST between them

One process per agent (`services/`), each told its own name, port and successor URL by configuration.
**Choreography, not orchestration**: a service calls its own successor's `POST /process`. The chain is
synchronous, so the verdict unwinds and one `POST` still answers with the final outcome.

What a network hop needs that a file drop did not:

- **Idempotency** on `message_id` + the active pack, persisted. A replay returns the first answer
  (`idempotent_replay: true`) and writes no second result file.
- **Per-hop timeout and bounded retries**, with a hard distinction between a downstream **4xx**
  (a verdict — propagate, never retry) and a **transport fault** (retry, then `503 upstream_unavailable`
  flagged `retryable`, safe precisely because hops are idempotent).
- **The journal survives**: every hop appends to `shared/audit/audit-log.jsonl`; the last hop writes
  exactly one result file. That is CR-02's "files under the hood for logging", literally.

**Two transports on purpose.** `--transport inprocess` for the batch CLI and the pre-CR-02 suite,
`--transport rest` for the mesh. `test_rest_and_inprocess_transports_agree` asserts they never disagree
on a verdict — the transport is provably not part of the decision.

Over REST the sample reproduces §8 exactly: 5×`200`, `409` at compliance, 2×`422` at the validator.

---

## 4. The REST gateway and the error contract

16 routes, standard library only (`http.server`) — the "runs on a bare Python install" property
survives, and `demo.sh` needs no dependency.

`POST /transactions` · `/transactions/batch` · `GET /transactions[/{id}]` · `GET /agents` ·
`POST /agents/{name}/process` · `POST /pipeline/chain` · `POST /pipeline/run` · `GET /rules` ·
`GET /errors` · `GET /summary[.md]` · `GET /audit` · `GET /` (the presentation)

**Errors are RFC 9457 `problem+json`**, from one catalog ([`docs/errors.md`](homework-6/docs/errors.md),
served live at `GET /errors`):

- **422** rejected · **409** held — a *business verdict*. The result **is** stored, so `Location` is
  real and `GET /transactions/{id}` works.
- **400** is reserved for a malformed *request*: bad JSON, bad query, or a schema violation reported
  field by field by `gateway/validation.py`. That module is deliberately **not** a second copy of the
  business rules — it checks shape and types (including "send money as a decimal string"), the pipeline
  keeps authority over domain rules.
- **503** for an unreachable downstream service; **5xx never carries an upstream exception string** —
  the catalog's generic detail goes out, the real cause goes to the log, and `request_id` ties them
  together. That same id appears in the response header, the problem body and the audit journal.

---

## 5. `demo.sh` — one command, zero manual steps

```bash
cd homework-6 && ./demo.sh
```

Eight checked steps: validation dry-run → default-pack run → strict-pack run **with a printed diff of
what changed** → one HTTP service per agent plus the gateway on free ports → live submissions with the
hop-by-hop trace → tests and the coverage gate → the MCP server. A `trap` stops everything it started
on success, on failure and on `Ctrl-C`; it exits non-zero on the first failure and names the step.
Transcript: `docs/sample-run/demo.log`. Flags: `--no-tests`, `--keep-running`, `--base-port`, `--port`.

**The demo earned its keep — it found three real bugs**, all fixed in this PR:

1. Subprocess services computed the topology from the *default* base port, not the one in use, so only
   the first hop ever worked (now the base port is passed to every child; the launcher also refuses to
   start on an occupied port, naming it).
2. A shell here-doc was the formatter's stdin, so the piped JSON never reached it (moved to
   `scripts/demo_render.py`).
3. The per-request rule-pack override never reached the mesh (now travels as `X-Policy-Rules`,
   forwarded hop to hop).

---

## 6. The interactive presentation

[`docs/presentation.html`](homework-6/docs/presentation.html) — self-contained, theme-aware, and it
**runs the demo from the page**: buttons submit real transactions and the flow diagram animates the
actual hops from the response's `trace` (order and statuses are real; only the pacing is
presentational). Served by the gateway at `/`, so it is same-origin with the API and connects by
itself. Opened as a file it degrades to offline mode on recorded responses and says how to get live
data.

```bash
cd homework-6 && .venv/bin/python -m gateway --port 8080    # → http://127.0.0.1:8080/
```

---

## 7. Verification

```
442 passed · coverage 90.72 % · gate PASSED (floor 80 %)
./demo.sh                          8/8 PASS
integrator.py                      exit 0, reconciled=yes, 8/8 terminal
integrator.py --rules policy-strict §8b reproduced
REST chain                         §8 reproduced: 5×200, 409, 2×422
verify_mcp_server.py               2 tools + 1 resource over real stdio
python3 integrator.py              still works with no virtualenv (stdlib-only pipeline)
```

Every test runs in `tmp_path` on ephemeral ports, so the suite cannot collide with a running demo.
New test files: `test_rule_engine.py`, `test_policy_engine.py`, `test_api_gateway.py`,
`test_services.py`. Only **two** pre-existing tests changed, both asserting pipeline *shape* (claimed
message count, the set of agents in the journal) — a sixth agent necessarily moves both. No test of a
monetary value, rejection code, risk score, compliance decision or masking rule changed.

---

## 8. Screenshots

The AI session that produced the base implementation: `6_1` … `6_25` in
[`docs/screenshots/`](homework-6/docs/screenshots/), indexed line by line in its
[README](homework-6/docs/screenshots/README.md).

Evidence panels — **rendered from real captured command output** by
[`scripts/capture_evidence.py`](homework-6/scripts/capture_evidence.py), each with its raw transcript
committed in [`docs/sample-run/`](homework-6/docs/sample-run/):

**CR-02 — agents as microservices, REST between them**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/rest-chain.png?raw=true" width="900">

**CR-01 — behaviour is configuration: the same input under two rule packs**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/rule-packs.png?raw=true" width="900">

**The pipeline over the file journal**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/pipeline-run.png?raw=true" width="900">

**Tests and coverage**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/test-coverage.png?raw=true" width="900">

**The coverage-gate hook: silent, passing, and blocking with exit code 2**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/hook-trigger.png?raw=true" width="900">

**MCP — context7 lookups and the custom server over stdio**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/mcp-interaction.png?raw=true" width="900">

<details>
<summary>Session start, spec generation, and the <code>/run-pipeline</code> skill</summary>

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/6_1.png?raw=true" width="900">
<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/specification.png?raw=true" width="900">
<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/skill-run-pipeline.png?raw=true" width="900">
</details>

> **Provenance, stated plainly.** The `6_*` images are ordinary screen captures of the Claude Code
> session. The evidence panels are **rendered from genuinely captured stdout/stderr and exit codes** —
> not OS screen grabs, not mock-ups. Every line is checkable against its `.txt` transcript and the
> script regenerates all of them. Details in
> [`docs/screenshots/README.md`](homework-6/docs/screenshots/README.md).

---

## 9. AI tooling and what I verified myself

**Claude Code (Opus 5)**, MCP: `context7` for documentation plus the custom `pipeline-status` server
this project builds.

Three documented context7 lookups ([`research-notes.md`](homework-6/research-notes.md)) with the line of
code each changed. The two that mattered: FastMCP's **in-memory client**, which turned the MCP tests
from subprocess spawns into ~0.2 s; and CPython's `decimal` docs — the context default is
`ROUND_HALF_EVEN`, which is why rounding is explicit `ROUND_HALF_UP`, and `Decimal(1.1)` keeps binary
error, which is why `parse_amount` refuses floats and why the rule engine refuses float operands.

Skills: `/write-spec`, `/run-pipeline`, `/validate-transactions`. Hook: a `PreToolUse` gate blocking
`git push` below 80 % coverage, also available as a git `pre-push` hook and a CLI.

**Verified by running, not by trusting a summary**: the seven commands in §7; that no result file,
report, journal line or HTTP response contains `ACC-`; that `--uninstall` restores the repository root
byte-for-byte; and that the PR diff contains only `homework-6/`.

---

## 10. Notes for the reviewer

- Start with `./demo.sh`, then `./demo.sh --keep-running` and open the printed URL for the presentation.
- `shared/` is git-ignored (regenerated per run); a complete copy of one real run is committed at
  `docs/sample-run/shared/`.
- Root-level Claude Code wiring (hook, slash commands, MCP entries) is **not** in this PR — it is one
  reversible command, `scripts/install_claude_integration.py` (`--status` / `--uninstall`).
- Explicit non-goals, so nothing looks forgotten: no auth/TLS/rate limiting on a loopback-only demo
  surface (permissive CORS is deliberate, so the presentation works from `file://`); no broker; no
  database — the file journal is the storage model. Sanctions list, watchlist and FX rates are labelled
  in code as illustrative fixtures.
