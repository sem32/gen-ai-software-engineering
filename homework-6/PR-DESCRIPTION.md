# Homework 6 — AI-Powered Multi-Agent Banking Pipeline (final capstone)

**Created by Simon Darienko** · branch `homework-6-submission` → `main` · everything in this PR
lives inside [`homework-6/`](homework-6/), nothing outside that folder is touched.

---

## 1. Summary

The assignment has two layers and this PR delivers both.

**The outer layer — four meta-agents**, i.e. AI workflows that *build* software: one produces the
specification, one generates the pipeline code, one writes the unit tests and enforces a coverage
gate, one writes the documentation.

**The inner layer — what they built**: a file-based **multi-agent banking transaction pipeline**.
Five agents that never call each other; they exchange JSON messages through shared directories, the
way batch banking systems actually do. A record enters from `sample-transactions.json`, is claimed
by the **validator**, scored by the **fraud detector**, screened by the **compliance checker**,
booked by the **settlement processor** and aggregated by the **reporting agent**. Once a run
finishes, a custom **FastMCP server** makes the results queryable by an LLM.

```
                       sample-transactions.json
                                  │
                        ┌─────────▼─────────┐
                        │    integrator     │  one protocol message per record
                        └─────────┬─────────┘
                          shared/input/
                                  │
       ┌──────────────────────────▼──────────┐
       │  transaction_validator              │──── invalid ───────────┐
       │  fields · amount · ISO 4217 · format│                        │
       └──────────────────────────┬──────────┘                        │
       ┌──────────────────────────▼──────────┐                        │
       │  fraud_detector    7 rules → 0-100  │                        │
       └──────────────────────────┬──────────┘                        │
       ┌──────────────────────────▼──────────┐                        │
       │  compliance_checker  sanctions/CTR  │──── held ──────────────┤
       └──────────────────────────┬──────────┘                        │
       ┌──────────────────────────▼──────────┐                        │
       │  settlement_processor  fee/net/date │──── settled ───────────┤
       └─────────────────────────────────────┘                        ▼
                                                             shared/results/
                                                                      │
                                                        ┌─────────────▼──────────┐
                                                        │    reporting_agent     │
                                                        └─────────────┬──────────┘
                                                             shared/reports/
                                                                      │
                                                  ┌───────────────────▼──────────┐
                                                  │  MCP "pipeline-status"       │
                                                  │  get_transaction_status      │
                                                  │  list_pipeline_results       │
                                                  │  pipeline://summary          │
                                                  └──────────────────────────────┘

  every hop appends to shared/audit/audit-log.jsonl  (ISO 8601 · agent · txn id · outcome,
  accounts masked ****NNNN) · unreadable messages go to shared/quarantine/ and the run continues
```

### The four meta-agents and their required "plus"

| Agent | Deliverable | Its "plus" |
|---|---|---|
| **1 — Specification** | [`specification.md`](homework-6/specification.md) (5 required sections + `IN-*` guardrails + `EC-*` edge cases + `T-0`…`T-9` low-level tasks), [`agents.md`](homework-6/agents.md) | **Skill**: [`/write-spec`](homework-6/.claude/commands/write-spec.md) |
| **2 — Code generation** | [`integrator.py`](homework-6/integrator.py), [`agents/`](homework-6/agents) (5 agents + protocol + base + results store), [`mcp/server.py`](homework-6/mcp/server.py) | **MCP context7**: 3 lookups documented in [`research-notes.md`](homework-6/research-notes.md) |
| **3 — Unit tests** | [`tests/`](homework-6/tests) — **232 tests, 99 % coverage**, [`scripts/coverage_gate.py`](homework-6/scripts/coverage_gate.py) | **Hook**: `PreToolUse` gate that **blocks `git push` below 80 %** |
| **4 — Documentation** | [`README.md`](homework-6/README.md), [`HOWTORUN.md`](homework-6/HOWTORUN.md) | **Requirement**: README carries the author's name — *Simon Darienko* |

### Engineering properties worth reviewing

- **Money is never a `float`.** Amounts stay strings on the wire, become `Decimal` exactly once at
  the validator boundary, and quantise `ROUND_HALF_UP` to the currency's minor unit (JPY → 0
  decimals, USD → 2). `parse_amount()` **raises `MoneyError` on a `float` input** — including
  `Decimal(1.1)`-style mistakes. The ledger invariant `fee + net_amount == amount` is asserted in
  code.
- **PII is masked by construction.** Accounts become `****NNNN` and the customer description is
  redacted before anything leaves the validator. `AuditLogger.record()` **raises rather than write**
  a record that still contains an unmasked account — the guard is a control, not a lint rule.
- **Fail closed.** Missing country, absent fraud assessment, unparseable amount → hold or reject.
  There is no permissive `else` on a decision path.
- **Decision functions are pure** — no wall clock, no randomness. Timing rules read the
  transaction's own timestamp, so a run is reproducible; a test asserts two runs agree.
- **Exactly-once terminal outcome.** Every transaction ends in `shared/results/` with a status from
  the closed set `{rejected, held, settled}`; the integrator reconciles the counts and exits
  non-zero if it cannot.
- **The pipeline has no third-party dependencies** — `python3 integrator.py` runs on a bare
  interpreter. `fastmcp` is imported only by the MCP server.

---

## 2. Results on the supplied sample data

| Transaction | Amount | Risk | Compliance | Terminal status | Why |
|---|---|---|---|---|---|
| TXN001 | 1 500.00 USD | 0 (low) | cleared | **settled** | ordinary domestic transfer, fee 3.75 |
| TXN002 | 25 000.00 USD | 40 (medium) | cleared, CTR required | **settled** | above the 10 000 reporting threshold |
| TXN003 | 9 999.99 USD | 35 (medium) | cleared | **settled** | `structuring` — deliberately just under the threshold |
| TXN004 | 500.00 EUR | 40 (medium) | cleared | **settled** | `unusual_timing` 02:47 UTC + `off_hours_api` |
| TXN005 | 75 000.00 USD | 60 (high) | **held** | **held** | `high_value` + `very_high_value` → manual review |
| TXN006 | 200.00 XYZ | — | — | **rejected** | `unknown_currency:XYZ` |
| TXN007 | −100.00 GBP | — | — | **rejected** | `non_positive_amount` |
| TXN008 | 3 200.00 USD | 0 (low) | cleared | **settled** | ordinary domestic transfer |

**8 processed · 5 settled · 1 held · 2 rejected · `reconciled=yes`.**
This table is §8 of the specification and is asserted transaction-by-transaction in
`tests/test_integration.py` — it is a regression test, not a claim.

---

## 3. Screenshots

### 3.1 The AI-assisted work itself (`6_1` … `6_25`)

Real screen captures of the Claude Code session that produced this homework — one prompt, 30 m 35 s,
Claude Code v2.1.226 / Opus 5 (1M context). Full index with a line per image:
[`docs/screenshots/README.md`](homework-6/docs/screenshots/README.md).

**Session start — the prompt, the context7 calls, Agent 1 writing the spec**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/6_1.png?raw=true" width="900">

**Agent 2 — `protocol.py`, and the `require_masked` refinement that draws the PII boundary**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/6_2.png?raw=true" width="900">

**Agent 3 — the suite closes the last gaps: "99 % покрытия, 232 теста", then the coverage gate**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/6_17.png?raw=true" width="900">

**Task 3 — the slash command, the `PreToolUse` hook config and the optional reminder hook**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/6_19.png?raw=true" width="900">

**Task 4 — `mcp.json`, the MCP verification script, `research-notes.md`**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/6_20.png?raw=true" width="900">

**Closing report — the four-agent table and the five verification commands with their real output**

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/6_25.png?raw=true" width="900">

The remaining 19 (`6_3`–`6_16`, `6_18`, `6_21`–`6_24`) cover every file write and diff in between —
each agent module, every test file, the docs, and three self-corrections worth pointing at: `6_4`
(extracting a pure function out of the validator class), `6_16` (a wrong test assertion caught by
the first red run: 1 failed / 222 passed) and `6_22` (an inaccurate `Decimal(1.1)` quotation fixed
before it reached the PR).

### 3.2 Specification produced — Task 1 / Agent 1

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/specification.png?raw=true" width="900">

### 3.3 Pipeline running — Task 2 / Agent 2

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/pipeline-run.png?raw=true" width="900">

### 3.4 `/run-pipeline` skill executing — Task 3

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/skill-run-pipeline.png?raw=true" width="900">

### 3.5 Coverage-gate hook blocking a push — Task 3

Silent on a non-push command (exit 0) · passes on a real `git push` at 99.50 % · **exit code 2,
push blocked** when the floor is raised above the measured coverage.

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/hook-trigger.png?raw=true" width="900">

### 3.6 MCP — context7 lookups and the custom server over stdio — Task 4

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/mcp-interaction.png?raw=true" width="900">

### 3.7 Tests and coverage — Task 5

<img src="https://github.com/sem32/gen-ai-software-engineering/blob/homework-6-submission/homework-6/docs/screenshots/test-coverage.png?raw=true" width="900">

> **Provenance, stated plainly.** The six panels in 3.2–3.7 are **rendered from real captured
> command output** by [`scripts/capture_evidence.py`](homework-6/scripts/capture_evidence.py) — they
> are not OS screen grabs and not mock-ups. Each one has its raw transcript committed next to it in
> [`docs/sample-run/`](homework-6/docs/sample-run/), so every line can be verified, and the script
> regenerates all six from scratch. The `6_*` images in 3.1 are ordinary screen captures with no
> post-processing. Details in
> [`docs/screenshots/README.md`](homework-6/docs/screenshots/README.md).

---

## 4. AI tools used, and what I verified myself

**Tool**: Claude Code v2.1.226, model Opus 5 (1M context). **MCP servers**: `context7` for library
documentation, plus the custom `pipeline-status` server this homework builds.

**Workflow — spec first, code second**, exactly as the assignment's own tip recommends:

1. **One prompt** started it: *"сделай домашнее задание #6 согласно описанию в homework-6/TASKS.md"*
   (`6_1`). No pre-written plan was handed to the model.
2. **Agent 1** wrote `specification.md` before any code existed — objectives `MO-1…MO-6`, guardrails
   `IN-1…IN-7`, edge cases `EC-01…EC-15`, and one low-level task per component (`T-0`…`T-9`) with a
   prompt / file / function / details / acceptance block each. §8 of that spec is the expected
   outcome table, written **before** the pipeline could produce it.
3. **Agent 2** implemented `T-0`…`T-7` in build order, calling **context7** first for the two
   things most likely to be wrong from memory (below).
4. **Agent 3** wrote the suite and the gate; the `EC-*` ids from the spec became test names
   (`test_ec_11_friday_wire_settles_on_tuesday`).
5. **Agent 4** wrote the docs and the evidence capture.

**The three context7 lookups** (full write-up with the applied insight per file and line in
[`research-notes.md`](homework-6/research-notes.md)):

| # | Query | Library ID returned | What it changed |
|---|---|---|---|
| 1 | *"define `@mcp.tool` and `@mcp.resource` with a custom URI, and test the server in-memory with `Client`"* | `/prefecthq/fastmcp` (benchmark 82.71, 4 041 snippets) | the resource URI goes in the decorator argument; `Client(server)` runs the real MCP protocol in-process — so all six MCP tests use the in-memory transport (~0.2 s, no subprocess) and only the evidence script spawns a real stdio server |
| 2 | *"decimal: `quantize` with `ROUND_HALF_UP` … why float must not be used for money"* | `/python/cpython` (benchmark 77.12, 36 843 snippets) | CPython's context default is `ROUND_HALF_EVEN` (banker's rounding), so `quantize_money()` passes `ROUND_HALF_UP` explicitly; `Decimal(1.1)` keeps the binary error, so `parse_amount()` rejects `float` outright |
| 3 | FastMCP client transports (returned with query 1) | `/prefecthq/fastmcp` | two transports for two jobs: in-memory for tests, `StdioTransport` for the evidence script |

**What I verified myself, by running it** — not by trusting the model's summary:

```
agents/transaction_validator.py --dry-run  → 8 records: 6 valid, 2 invalid, nothing written to shared/
integrator.py                              → exit 0, reconciled=yes, 8 files in shared/results/
pytest                                     → 232 passed, 99 % coverage
scripts/coverage_gate.py --simulate-push   → PASSED 99.50 % ≥ 80 %; at floor 99.9 → exit 2, blocked
scripts/verify_mcp_server.py               → server up over stdio, 2 tools + 1 resource answering
python3 integrator.py                      → works without the venv (pipeline is stdlib-only)
scripts/install_claude_integration.py      → install → --status → --uninstall restores the root byte-for-byte
```

I also checked the things a summary would hide: that `docs/sample-run/shared/` is not swallowed by
the `.gitignore` rule (it needed an anchored `/shared/`), that no result file or audit line contains
`ACC-`, and that the PR diff contains **only** `homework-6/`.

---

## 5. Challenges encountered, and how they were addressed

**1. `homework-6/mcp/` shadows the installed `mcp` package.** The assignment asks for
`mcp/server.py`, but a directory named `mcp/` on `sys.path` becomes a namespace package and wins
over the `mcp` distribution that FastMCP itself imports — an `ImportError` that only appears once
the tests import `fastmcp`. Fixed structurally rather than by renaming: no `__init__.py` in `mcp/`,
`sys.path.append` (never `insert(0)`) in `server.py` and `integrator.py`, `tests/` deliberately has
no `__init__.py` so pytest inserts `tests/` rather than the project root, and `tests/conftest.py`
normalises `sys.path` however pytest was launched. Documented in `HOWTORUN.md` §13 with the symptom
that would bring you back to it.

**2. Where the PII boundary actually sits.** The first version asserted "no unmasked account
anywhere", which is wrong: the validator has to *see* the raw account in order to check its format.
The boundary is in-flight (`input`/`processing`/`output`, internal working state) versus terminal
(`results`, the audit trail, reports, MCP responses). `write_message(..., require_masked=True)` is
set only for terminal writes, and the validator masks from its own output onwards, so the assertion
holds where it matters (`6_2`).

**3. The first test run was red — and it was the test that was wrong.** 1 failed / 222 passed:
`test_summary_contains_no_unmasked_accounts` asserted `"****1001" in summary`, but the summary
legitimately carries no account field at all. The fix was to assert the masking on the result files
the summary is built from, not to weaken the assertion (`6_16`).

**4. `--cov=mcp/server.py` measured nothing.** pytest-cov resolved it as a module name, so the file
silently stayed out of the report. Switched to `--cov=mcp` (a directory path) — the server then
showed up at 90 %.

**5. Keeping the coverage gate honest.** A gate that only ever passes proves nothing, so it is
demonstrated in all three states — silent on a non-push command, passing on a real `git push`, and
blocking with exit code 2 — by raising the floor above the measured coverage rather than by
deleting tests.

**6. Screenshots I cannot take.** The assistant cannot grab the OS screen, so the six evidence
panels are rendered from genuinely captured stdout/stderr and exit codes, with the raw transcripts
committed alongside. That is stated in the PR, in `docs/screenshots/README.md` and in the images
themselves rather than left for a reviewer to discover. The 25 session captures supply the real
screen grabs.

**7. Keeping the change inside `homework-6/`.** Claude Code loads hooks, slash commands and MCP
servers from the repository root only. Instead of scattering files there, the root wiring is a
single reversible command,
[`scripts/install_claude_integration.py`](homework-6/scripts/install_claude_integration.py)
(`--status` / `--uninstall`), which merges rather than overwrites, tags its own hook entries,
backs up an existing `settings.json` and refuses to clobber a real file. Verified that
`--uninstall` restores the root exactly.

---

## 6. How to run and verify

```bash
git checkout homework-6-submission
cd homework-6
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python agents/transaction_validator.py --dry-run   # 8 records: 6 valid, 2 invalid
.venv/bin/python integrator.py                               # exit 0, reconciled=yes
.venv/bin/pytest                                             # 232 passed, 99 % coverage
.venv/bin/python scripts/coverage_gate.py --simulate-push    # PASSED: 99.50 % >= 80 %
.venv/bin/python scripts/verify_mcp_server.py                # all MCP calls completed
```

To try the slash commands and the hook inside Claude Code (the only step that touches the
repository root, and it is reversible):

```bash
.venv/bin/python scripts/install_claude_integration.py --git-hook
# restart Claude Code, then: /run-pipeline · /validate-transactions · /write-spec
.venv/bin/python scripts/install_claude_integration.py --uninstall
```

Step-by-step guide with troubleshooting: [`HOWTORUN.md`](homework-6/HOWTORUN.md).

---

## 7. Deliverables checklist

**Specification (Task 1 / Agent 1)**
- [x] `specification.md` — all 5 required sections, plus `IN-*` guardrails, `EC-*` edge cases and a
      Low-Level Task per agent with prompt / file / function / details / acceptance
- [x] `agents.md` — extended with this project's context and rules
- [x] `.claude/commands/write-spec.md` — skill that generates a spec from the template

**Pipeline (Task 2 / Agent 2)**
- [x] `integrator.py` + 5 cooperating agents (minimum was 3): `transaction_validator`,
      `fraud_detector`, `compliance_checker`, `settlement_processor`, `reporting_agent`
- [x] File-based protocol through `shared/{input,processing,output,results}` (+ `reports`, `audit`,
      `quarantine`)
- [x] `research-notes.md` — 3 context7 queries with library id and applied insight

**Skills & hooks (Task 3 / Agent 3)**
- [x] `.claude/commands/run-pipeline.md`
- [x] `.claude/commands/validate-transactions.md`
- [x] `.claude/settings.json` — coverage-gate hook blocking `git push` below 80 %, plus an optional
      `PostToolUse` reminder; the same gate is available as a git `pre-push` hook and as a CLI

**MCP (Task 4)**
- [x] `mcp.json` — `context7` + `pipeline-status`
- [x] `mcp/server.py` — `get_transaction_status`, `list_pipeline_results`, `pipeline://summary`

**Tests & docs (Task 5 / Agent 4)**
- [x] `tests/` — 232 tests, unit per agent + end-to-end integration, **99 %** coverage (gate 80 %,
      target ≥ 90 %), every test isolated in `tmp_path`
- [x] `README.md` — author's name, ASCII architecture diagram, tech stack table
- [x] `HOWTORUN.md` — numbered steps from setup to demo, with troubleshooting
- [x] `docs/screenshots/` — 25 session captures + 6 evidence panels, indexed
- [x] This PR description embeds the screenshots and stands on its own

---

## 8. Notes for the reviewer

- The diff is confined to `homework-6/`. Nothing at the repository root is modified by this PR.
- `shared/` is git-ignored (it is regenerated by every run); a complete copy of one real run —
  results, reports and the audit trail — is committed at `homework-6/docs/sample-run/shared/`.
- The sanctions list, the account watchlist and the FX rate table are labelled in code as
  illustrative demonstration fixtures, not screening feeds.
- `integrator.py` exits non-zero when reconciliation fails; `test_main_no_reset_keeps_previous_results`
  covers that path deliberately.
