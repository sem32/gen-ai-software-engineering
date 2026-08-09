# Homework 3 — Specification-Driven Design: Virtual Card Lifecycle

> **Author / Student Name**: Simon Darienko
> **Homework**: 3 — Specification-Driven Design (documents only, no implementation)
> **AI Tools Used**: Claude Code (Opus 5)

---

## 1. Student & task summary

This submission is a **specification package** for the virtual card lifecycle feature of a retail neobank: creating a virtual card, freezing/unfreezing it, setting spending controls, revealing card details, viewing transactions, replacing a compromised card, and closing it — plus the issuer-side authorization decision the card processor calls back into.

No code is delivered, by design. The artifact under review is the specification: how the problem is decomposed, how requirements trace from a single north-star objective down to individual implementable tasks, and how failure modes, verification and performance targets are built into the spec rather than appended to it.

### Deliverables

| File | What it is |
|---|---|
| [`specification.md`](./specification.md) | The layered specification: high-level objective → stakeholders → 10 mid-level objectives → domain model & state machine → 17 non-functional/policy requirements → 18 implementation guardrails → beginning/ending context → **30 low-level tasks** with acceptance criteria → **36 edge cases** → verification strategy → 13 performance targets → traceability matrix |
| [`agents.md`](./agents.md) | How an AI coding agent must behave in this repository: stack assumptions, domain rules, code style, testing & verification expectations, security/compliance constraints, edge-case doctrine, working agreement, definition of done |
| [`.cursor/rules/`](./.cursor/rules) | Editor/AI rules, four scoped files: `00-core-fintech-defaults.md` (always on), `10-architecture-and-naming.md`, `20-testing-and-verification.md`, `30-security-privacy-audit.md` |
| [`docs/screenshots/`](./docs/screenshots) | Evidence of the AI-assisted workflow that produced this package (see §4) |
| `README.md` | This file — rationale and industry practices |

> **Note on the rules directory**: `.cursor/rules/` starts with a dot and may be hidden in some file browsers. It is the single set of editor/AI rules required by the task. `agents.md` is the tool-agnostic companion consumed by Claude Code / Copilot / Codex; the Cursor rules are the narrower, glob-scoped enforcement layer.

### Chosen domain and why

Virtual cards were the suggested example, and they are the richest small feature in consumer FinTech: a real state machine (7 states, transitions with different authorities), a genuinely hard concurrency problem (two authorizations racing for the last euro of a daily cap), a hard latency constraint imposed from outside (the card scheme's authorization window), a strict data-handling boundary (PCI DSS — the PAN must never enter our systems), and a natural ops/compliance surface (administrative lock under dual control). That combination makes the layering exercise meaningful instead of decorative.

---

## 2. Rationale — why the specification is written this way

### 2.1 Layering: each level answers a different question

The layers are not a formatting convention; each exists to answer one question and to be checkable against the level above it.

| Layer | Question it answers | Design decision made here |
|---|---|---|
| High-level objective (§1) | *Why does this exist?* | One sentence, with two **numbers in it** (card usable in < 60 s, freeze effective in < 2 s) and an explicit one-sentence scope boundary. A north star without a boundary invites scope creep; a north star without numbers cannot be falsified. |
| Stakeholders (§2) | *Who observes success?* | Six stakeholders, each with an observable success signal — this is where the ops/compliance view stops being an afterthought. |
| Mid-level objectives (§3) | *What changes in the world?* | 10 objectives phrased as observable states ("a frozen card stops spending within 2 s"), not activities ("implement freeze"). Every one is directly falsifiable, which is what makes §10 possible. |
| Domain model + state machine (§4) | *What are the legal moves?* | A full 7×7 transition table with **who** may perform each transition and which require dual control. This single table drives task T-01, its 49-case test, and the "no permissive default" rule on the authorization path. |
| Non-functional & policy (§5) | *How well, how safely?* | Split into security / privacy / governance / reliability / performance, each requirement individually numbered so tasks and the threat model can cite it. |
| Implementation notes (§6) | *What must a builder never do?* | 18 binding guardrails (money as minor units, ULID identifiers, idempotency semantics, optimistic locking, error taxonomy, hash-chained audit, outbox, cursor pagination…). Stated as invariants an agent can be held to, not as advice. |
| Context (§7) | *What exists before and after?* | A concrete list of pre-existing services with their exact responsibilities, and a full target file tree annotated with the task that creates each file. An agent that knows the destination file layout stops inventing one. |
| Low-level tasks (§8) | *What do I do on Monday?* | 30 tasks, dependency-ordered, each with prompt / files / functions / details / **Serves** / **acceptance criteria**. |

### 2.2 Why 30 tasks instead of a handful

Three generic bullets would hide exactly the work that is hard in this domain. The decomposition deliberately gives first-class task status to things that are usually treated as "infrastructure that will happen somehow": idempotency (T-04), the audit chain (T-06), the processor port and its deterministic fake (T-08), the transactional outbox (T-24), redaction and observability (T-26), retention/erasure (T-27), reconciliation (T-28), and the threat model (T-30). Each is ordered so it only depends on earlier tasks, so the list is executable top-to-bottom by an agent or by a team splitting work.

Acceptance criteria are written as checkboxes phrased so a reviewer can mechanically verify them ("6th active card → `409 card_issuance_cap_reached`"), not as aspirations ("issuance should be limited").

### 2.3 How the performance targets were chosen

Every number in §11 is explicitly labelled an **ASSUMED TARGET** with a written rationale, because no production baseline exists for a homework system. Presenting invented numbers as measured facts would be the worse failure. The reasoning went:

- **Start from external constraints, not from wishes.** The authorization budget (`PERF-01`: p99 ≤ 150 ms, hard timeout 250 ms) is derived from the fact that the card scheme allows only a few seconds for the whole authorization round trip, of which the processor reserves a fraction for the issuer's own decision hop. That is a constraint imposed on us, so it anchors everything else on the hot path.
- **Then pick the safety-critical number.** `PERF-04` (freeze → decline, p99 ≤ 2 s) is the one target where being slow is a *trust* failure, not a UX annoyance: a customer who taps freeze believes spending stopped. It is stated as a time-to-consistency budget and given a synthetic production probe (`V-11`), because it is the only way to know it holds in reality.
- **Then UX thresholds.** List and reveal latencies (`PERF-05`, `PERF-06`) sit under the ~400–500 ms range where an in-app interaction still feels immediate.
- **Then capacity, from a stated population.** `PERF-07` (300 req/s sustained, 900 peak) is derived from an assumed ~500 k active cards with a 3× peak factor, so the assumption can be challenged directly rather than argued about in the abstract.
- **Rate limits are protective, not performance.** They are listed alongside (`PERF-08`) because in FinTech they are part of the performance contract in practice: the reveal limits are the tightest because reveal is the highest-value target for an attacker.

Every target also states its **measurement method** (server-side histograms, 28-day rolling window) and is tied to an error-budget policy, so a number cannot quietly become decoration.

### 2.4 How the verification depth was chosen

Verification depth follows blast radius, not uniform coverage:

- **Objective-level verification** (§10.2): each of the 10 mid-level objectives has ≥ 2 named verification activities (`V-01`…`V-29`). If an objective could not be verified, it was rewritten until it could — that constraint is what forced the objectives to be observable in the first place.
- **Highest rigour where errors are irreversible or invisible**: 100 % branch coverage on the state machine, the decision function, `Money` and idempotency; a 100-iteration deterministic concurrency test for the double-spend race; tamper tests for the audit chain; PAN-shape scanning across DB, logs, responses and exports.
- **Fault injection as a first-class category**, because in payments the interesting behavior is the degraded behavior. The processor fake (T-08) exists specifically so every failure mode in §9 has a test rather than a paragraph.
- **Human gates where automation cannot decide** (§10.3): five checkpoints — design, security, compliance, performance, release readiness — each with a named owner and an exit criterion. Segregation of duties and PCI scope are judgement calls; pretending a test suite settles them would be dishonest.
- **Anti-gaming rules in `agents.md`**: coverage is a floor, a flaky concurrency test is treated as a real race, and "done" requires pasted command output. Specifications that omit these get agents that make tests pass instead of making systems correct.

### 2.5 Why edge cases live in the spec, not in a bug tracker

§9 lists 36 numbered edge cases, each with an expected **user-visible outcome** *and* an **audit/compliance implication**, because in a regulated product those are two different requirements and only one of them is visible from the UI. They are cross-referenced from the traceability matrix, so implementing task T-15 tells you exactly which edge cases you owe tests for (`EC-09`, `EC-10`, `EC-21`, `EC-22`, `EC-34`, `EC-36`). Several encode decisions that are easy to get subtly wrong and expensive to fix later — lowering a limit never applies retroactively (`EC-11`), a refund does not restore a previous month's headroom (`EC-18`), a capture arriving before its authorization is parked rather than dropped (`EC-16`), local state stays authoritative when processor propagation fails (`EC-19`).

### 2.6 Traceability

Section 12 closes the loop: every task cites the objectives it serves, the verification activities that prove it, and the edge cases it must handle. The coverage check at the bottom states the invariant explicitly — every objective has ≥ 2 tasks and ≥ 2 verification activities, every edge case maps to a task, and no task exists without an objective. That last one matters most: it is the mechanism that catches work nobody asked for.

---

## 3. Industry best practices applied, and where they appear

### FinTech / payments

| Practice | Where |
|---|---|
| **PCI DSS scope minimisation** — never store PAN/CVV; hold only a processor token and `pan_last4`; processor-hosted reveal | `specification.md` §5.1 `NFR-01`, §4.1, §6 `IN-08`, T-11; `.cursor/rules/00-core-fintech-defaults.md` rule 2 |
| **PSD2 / SCA step-up authentication** with a freshness window before revealing credentials | §5.1 `NFR-02`, T-11, T-18; `.cursor/rules/30-security-privacy-audit.md` |
| **Money as integer minor units**, currency-aware, no floats, no cross-currency arithmetic | §6 `IN-01`, T-02, `agents.md` §2.1, `.cursor/rules/00` rule 1 |
| **Authorization holds vs settlement**, partial capture, reversal, hold expiry | §4.1 `SpendCounter`, T-15, T-17, `EC-15`–`EC-18` |
| **Daily reconciliation with typed breaks** and auto-heal only for the safe class | T-28, `V-16`, §9 `EC-19` |
| **Fail-closed authorization** — decline on timeout or dependency failure, never approve by default | §6 `IN-12`, T-15, `EC-21`, `.cursor/rules/00` rule 3 |
| **Velocity controls and card-testing-attack response**, including notification storm suppression | T-23, T-25, `EC-26`, `EC-28`, `PERF-08` |
| **Customer-safe decline messaging** that never leaks fraud-rule internals | §6 `IN-17`, T-13, T-23, `agents.md` §6.6 |

### Regulated-environment governance

| Practice | Where |
|---|---|
| **Tamper-evident, append-only audit trail** (hash chain, `INSERT`-only DB grant, written in the same transaction as the change) | §5.2 `NFR-09`, §6 `IN-09`, T-06, `V-18`/`V-19`, `EC-32` |
| **Audit of failed attempts**, not only successes | §5.2 `NFR-09`, `EC-03`, `EC-08`, `EC-30`, `EC-31` |
| **Maker-checker / segregation of duties** for privileged ops actions, enforced in code | §5.3 `NFR-11`–`NFR-12`, T-21, `V-22`, `EC-30` |
| **Least privilege + `404` instead of `403`** so authorization does not leak existence | §5.1 `NFR-06`, §6 `IN-06`, T-07, `V-23` |
| **GDPR retention, erasure and legal-hold precedence**; pseudonymisation that preserves chain verifiability | §5.2 `NFR-07`–`NFR-08`, T-27, `V-28`/`V-29`, `EC-35` |
| **Auditor-facing export** that is reproducible and independently verifiable | T-22, §10.3 CP-3 |
| **STRIDE threat model with mitigations linked back to requirements** | T-30, §10.3 CP-2 |
| **Data map maintained as code artifact**, updated in the same PR as any data change | `NFR-07`, T-30, `.cursor/rules/30` |

### Distributed-systems and API engineering

| Practice | Where |
|---|---|
| **Idempotency keys** with request-hash conflict detection and stored-response replay | §6 `IN-03`, T-04, `EC-02`–`EC-03` |
| **Optimistic locking + atomic conditional counter updates** to eliminate lost updates and double-spend | §6 `IN-04`, T-15, `EC-07`, `EC-09`, `V-08` |
| **Transactional outbox** with at-least-once delivery and per-aggregate ordering | §6 `IN-10`, T-24 |
| **Webhook security**: mTLS + HMAC over the raw body, timestamp window, replay rejection, verify-before-parse | §5.1 `NFR-03`, T-10, `EC-23` |
| **Event dedupe and out-of-order tolerance** on every consumer | T-10, T-17, `EC-16`, `EC-22` |
| **Ports & adapters with a deterministic fake** enabling contract and fault-injection testing | §6 `IN-11`, T-08, §10.1 |
| **Timeouts, bounded retries with jitter, circuit breakers**; retries only on idempotent operations | §5.4 `NFR-17`, T-08 |
| **RFC 9457 `problem+json` with a closed error-code enum** treated as part of the API contract | §6 `IN-05`, T-05 |
| **Cursor pagination with a total sort order**; no `OFFSET`, no unbounded counts | §6 `IN-13`, T-16, `V-15` |
| **Expand → migrate → contract** migrations, reversible and never edited after application | §6 `IN-16`, `.cursor/rules/30` |
| **Correlation IDs propagated** to the processor, the outbox, the audit record and every log line | §6 `IN-18`, T-26 |
| **SLOs with error-budget policy, RPO/RTO**, and a synthetic probe for the safety-critical path | §5.4 `NFR-14`–`NFR-15`, §11, `V-11` |

### AI-assisted development

| Practice | Where |
|---|---|
| **Explicit precedence order** between spec, agent guide and editor rules, with "more restrictive wins" | `agents.md` header, `.cursor/rules/00` |
| **Stop-and-ask triggers** instead of guessing a requirement in a regulated domain | `agents.md` §7, `.cursor/rules/00` |
| **Evidence-based completion** — no "done" without pasted command output; never weaken a test to make it green | `agents.md` §4, `.cursor/rules/20` |
| **Scope discipline** — one task per PR, no opportunistic refactors | `agents.md` §7.5, `.cursor/rules/00` rule 6 |
| **Architecture tests as guardrails an agent cannot rationalise away** (no `status` writes outside the state machine, no `app.infrastructure` import in the domain, every endpoint present in the authorization matrix) | T-01, T-07, T-15, `.cursor/rules/10` |
| **Glob-scoped rules** so security rules load for handlers/adapters/migrations and testing rules load for test code | `.cursor/rules/*` frontmatter |
| **A definition of done as a paste-able checklist** | `agents.md` §8, `.cursor/rules/20` |

### Assumptions kept honest

All invented numbers are labelled: the eight open questions in §14 (card cap, limit ceiling, retention period, auto-lock policy, refund-window semantics, settlement window, multi-currency, PCI scope confirmation) each carry a current assumption **and a named decision owner**, and §11 marks every target as an assumed value with its rationale. The intent is that a reviewer can disagree with a specific number without having to re-derive the whole document.

---

## 4. AI-assisted workflow and evidence

**Tool**: Claude Code v2.1.226, model Opus 5 (1M context), run from the repository root.

**Workflow**: a single task-scoped session rather than a chat-and-paste loop.

1. The agent read `homework-3/TASKS.md` and `specification-TEMPLATE-example.md` first, plus `homework-2/README.md` and the root `README.md` to pick up the repository's authoring conventions.
2. The domain (virtual card lifecycle) was chosen from the options offered in `TASKS.md` on the reasoning given in §1.
3. Artifacts were produced in dependency order — `specification.md` first, because `agents.md` and the Cursor rules are downstream of the guardrails and the state machine defined there. This is why the three documents cross-reference the same `IN-*` / `NFR-*` / `T-nn` ids instead of restating rules in three different vocabularies.
4. Counts and internal consistency (30 tasks, 36 edge cases, 17 NFRs, 18 guardrails, 13 performance targets) were verified with `grep`/`wc` against the finished file, not asserted from memory.

**What I verified myself**: the traceability invariant (every task cites an objective, every objective has ≥ 2 verification activities, every edge case maps to a task); that the performance numbers are consistent with the card-scheme constraint they are derived from; and that no rule in `agents.md` or `.cursor/rules/` contradicts a guardrail in the specification.

**Screenshots** (`docs/screenshots/`) — the session that produced this package:

| File | Shows |
|---|---|
| `3_1.png` | Session start: the task prompt, the agent reading `TASKS.md` and the template, and `specification.md` being written (916 lines) |
| `3_2.png` | `agents.md` written, followed by the four glob-scoped `.cursor/rules/` files with their frontmatter |
| `3_3.png` | The security/privacy/audit rule file and `README.md` being written |
| `3_4.png` | Final summary of the delivered package and its contents |
