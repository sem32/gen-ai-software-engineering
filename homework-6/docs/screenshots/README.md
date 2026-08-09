# Screenshots

> **Author / Student**: Simon Darienko · Homework 6 (capstone)

Two sets of images live here.

- **`6_1.png` … `6_25.png`** — real screen captures of the Claude Code session that built this
  homework, in chronological order. This is the AI-assisted work itself: prompts, tool calls, file
  writes, diffs and the model's own commentary.
- **`specification.png`, `pipeline-run.png`, `test-coverage.png`, `skill-run-pipeline.png`,
  `hook-trigger.png`, `mcp-interaction.png`** — the six evidence panels the assignment asks for,
  each rendered from the real captured output of the command it shows (see *Provenance* below).

---

## Set 1 — the AI session, start to finish (`6_1` … `6_25`)

Claude Code v2.1.226, Opus 5 (1M context), one session, **30 m 35 s** wall clock.

| # | What it shows |
|---|---|
| `6_1` | Session start and the prompt *"сделай домашнее задание #6 согласно описанию в homework-6/TASKS.md"*. Environment probe, **4 context7 calls**, then Agent 1 writing `specification.md` (552 lines) and `agents.md` (197 lines) |
| `6_2` | Agent 2 starts: `agents/protocol.py` (457 lines) — message contract, `Decimal` money helpers, PII masking, audit logger. Then the `write_message(..., require_masked=...)` refinement that draws the in-flight / terminal PII boundary |
| `6_3` | `agents/base.py` (the shared drain loop) and the first `agents/transaction_validator.py`, followed by the PEP 366 shim so the module also runs as a plain script |
| `6_4` | Refactor: `validate()` extracted from the class into the module-level pure function `validate_transaction()` |
| `6_5` | The rest of that diff — currency, timestamp, account-format and same-source checks |
| `6_6` | `_check_amount()` (rejects `float`, non-positive, too many decimals) and the start of `redact_transaction()` |
| `6_7` | `redact_transaction()` — masks accounts, redacts the description — and the final `TransactionValidator` class |
| `6_8` | The validator CLI: `dry_run()` / `render_dry_run()`, the `--dry-run` mode that writes nothing under `shared/` |
| `6_9` | Validator finished; `agents/fraud_detector.py` (191 lines, 7 scoring rules) and `agents/compliance_checker.py` (126 lines, fail-closed AML screening) |
| `6_10` | `agents/settlement_processor.py` (106), `agents/reporting_agent.py` (216), `agents/results_store.py` (100) |
| `6_11` | `agents/__init__.py`, `integrator.py` (167) and `mcp/server.py` (64) — the custom FastMCP server |
| `6_12` | **First green pipeline run** ("точно воспроизводит таблицу §8 спецификации"), then Agent 3 starts: `tests/conftest.py`, `test_protocol.py` (335), `test_transaction_validator.py` (260) |
| `6_13` | `test_fraud_detector.py` (208), `test_compliance_checker.py` (143), `test_settlement_processor.py` (134) — each tagged with the `EC-*` edge cases it covers |
| `6_14` | The `completed_run` fixture (a full pipeline run inside `tmp_path`), `test_reporting_agent.py`, `test_results_store.py` |
| `6_15` | `test_integration.py` (193 — the §8 outcome table), `test_mcp_server.py` (108 — in-memory MCP transport), `pytest.ini` with the coverage flags |
| `6_16` | First run was **1 failed / 222 passed**: fixing the over-eager PII assertion, and switching `--cov=mcp/server.py` to `--cov=mcp` so the server is measured |
| `6_17` | `test_base_agent.py` closes the last gaps → **"99% покрытия, 232 теста"**. Agent 3's gate begins: `scripts/coverage_gate.py` (127 lines) |
| `6_18` | `scripts/pre-push` (git-level gate) and the slash commands `write-spec.md`, `run-pipeline.md` |
| `6_19` | `validate-transactions.md`, `.claude/settings.json` (the `PreToolUse` coverage-gate hook) and the optional `pipeline_reminder.py` `PostToolUse` hook |
| `6_20` | Task 4: `mcp.json` (context7 + pipeline-status), `scripts/verify_mcp_server.py`, and `research-notes.md` documenting the context7 lookups |
| `6_21` | Agent 4: `README.md` (235), `HOWTORUN.md` (237), `requirements.txt`, `.gitignore` |
| `6_22` | `scripts/capture_evidence.py` (280) — and a correction to the `Decimal(1.1)` digits quoted in the MCP panel, so the rendered image states the value accurately |
| `6_23` | The `specification` capture step added, plus this `docs/screenshots/README.md` |
| `6_24` | `.gitignore` fix (`/shared/` anchored so `docs/sample-run/shared/` stays committed) and `PR-DESCRIPTION.md` |
| `6_25` | The session's closing report — the four-agent table, the five verification commands with their real output, the screenshot provenance caveat, and what was deliberately left to the human |

Worth noting from the sequence: `6_4`, `6_16` and `6_22` are **self-corrections** — an extracted
pure function, a wrong test assertion, and an inaccurate quotation fixed before it reached the PR.

---

## Set 2 — the six evidence panels

| File | Shows | Raw transcript |
|---|---|---|
| `specification.png` | **Agent 1 / `/write-spec`** — the section outline of `specification.md` and the §8 outcome table that `tests/test_integration.py` asserts | [`../sample-run/specification.txt`](../sample-run/specification.txt) |
| `pipeline-run.png` | **`python integrator.py`** — the full multi-agent run: per-agent progress, the results table, per-currency volumes, `reconciled=yes`, exit code 0 | [`../sample-run/pipeline-run.txt`](../sample-run/pipeline-run.txt) |
| `test-coverage.png` | **`pytest`** — 232 tests, per-module coverage, **99 % total** (gate floor 80 %, target ≥ 90 %) | [`../sample-run/test-coverage.txt`](../sample-run/test-coverage.txt) |
| `skill-run-pipeline.png` | **`/run-pipeline`** — the slash command's five steps executed in order, ending in the summary and the list of everything that did not settle | [`../sample-run/skill-run-pipeline.txt`](../sample-run/skill-run-pipeline.txt) |
| `hook-trigger.png` | **The coverage gate hook firing** — silent on a non-push command (exit 0), passing on a real `git push` at 99.50 %, and **blocking with exit code 2** when the floor is raised above the measured coverage | [`../sample-run/hook-trigger.txt`](../sample-run/hook-trigger.txt) |
| `mcp-interaction.png` | **Both MCP servers** — the three `context7` lookups Agent 2 made (library ids and what each returned), then the custom `pipeline-status` server driven over real stdio: capabilities, `get_transaction_status` × 3, `list_pipeline_results`, `pipeline://summary` | [`../sample-run/mcp-interaction.txt`](../sample-run/mcp-interaction.txt) · [full](../sample-run/mcp-interaction-full.txt) |

### Provenance — read this

The six panels in set 2 are **rendered from real captured command output**, not OS screen grabs and
not mock-ups. [`scripts/capture_evidence.py`](../../scripts/capture_evidence.py) runs each command
as a subprocess, records stdout, stderr and the exit code, writes the transcript to
[`../sample-run/`](../sample-run/) and draws the same text into a terminal-styled image. Every line
in a panel can be checked against its `.txt` transcript, and every command can be re-run:

```bash
cd homework-6
.venv/bin/python scripts/capture_evidence.py     # regenerates all six panels and transcripts
```

Two panels carry hand-written context above the captured output, and both are labelled as such in
the image:

- `skill-run-pipeline.png` and `specification.png` show the `> /run-pipeline` / `> /write-spec`
  invocation line and a short description of what the command instructs, because a slash command is
  executed by Claude Code rather than by a shell. Everything below the invocation block is real
  captured output of the exact commands the command file specifies.
- `mcp-interaction.png` shows the `context7` calls as the tool name, arguments and returned library
  ids. Those calls were made through the MCP client during this build — `6_1` catches them live
  ("Called context7 4 times") — and the full write-up of each one is in
  [`../../research-notes.md`](../../research-notes.md).

The custom-MCP half of `mcp-interaction.png` is fully machine-generated: it is the output of
[`scripts/verify_mcp_server.py`](../../scripts/verify_mcp_server.py), which starts `mcp/server.py`
as a real stdio subprocess and speaks MCP JSON-RPC to it.

The `6_*` images in set 1 are ordinary screen captures and carry no post-processing.

---

## Also committed as evidence

[`../sample-run/shared/`](../sample-run/shared/) is a copy of one complete run's workspace:

- `results/` — the eight terminal result files, one per transaction, accounts masked `****NNNN`;
- `reports/pipeline-summary.json` and `.md` — the reporting agent's output;
- `audit/audit-log.jsonl` — the append-only audit trail, one line per agent operation.
