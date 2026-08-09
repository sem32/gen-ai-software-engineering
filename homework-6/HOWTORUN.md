# HOWTORUN — Homework 6 capstone

> **Author / Student**: Simon Darienko
> Every command below is run from the repository root unless the step says otherwise.
> Times are from a MacBook (Python 3.14.2): full run ≈ 0.2 s, full test suite ≈ 3 s.

---

## 1. Prerequisites

| Requirement | Note |
|---|---|
| **Python 3.12+** | developed and verified on 3.14.2 |
| **Node.js / `npx`** | only for the `context7` MCP server (`npx -y @upstash/context7-mcp@latest`) |
| **Claude Code** | only for the slash commands and the hook; the pipeline itself needs neither |

The **pipeline has no third-party dependencies** — `python3 homework-6/integrator.py` works on a
bare interpreter. The virtualenv below is needed only for the tests, the coverage gate and the MCP
server.

---

## 2. Create the environment

```bash
cd homework-6
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Verify:

```bash
.venv/bin/python -c "import fastmcp, pytest; print(fastmcp.__version__, pytest.__version__)"
# 3.4.6 9.1.1
```

---

## 3. Run the pipeline

```bash
cd homework-6
.venv/bin/python integrator.py
```

What happens:

1. `shared/` is created and cleared (`input/ processing/ output/ results/ reports/ audit/ quarantine/`).
2. Each record in `sample-transactions.json` becomes one protocol message in `shared/input/`.
3. The four message-driven agents each drain their inbox once, in order.
4. The reporting agent writes `shared/reports/pipeline-summary.{json,md}`.
5. A results table is printed and the run reconciles input count against terminal count.

Expected tail of the output — **8 processed, 5 settled, 1 held, 2 rejected, `reconciled=yes`**, exit
code `0`. A committed copy of a real run is in [`docs/sample-run/`](docs/sample-run/).

Useful flags:

```bash
.venv/bin/python integrator.py --sample path/to/other.json   # different input
.venv/bin/python integrator.py --shared /tmp/run-42          # different workspace
.venv/bin/python integrator.py --no-reset                    # keep what is already in shared/
.venv/bin/python integrator.py --quiet                       # no output, exit code only
```

---

## 4. Validate transactions without processing them (dry run)

```bash
cd homework-6
.venv/bin/python agents/transaction_validator.py --dry-run
```

Prints a table of total / valid / invalid plus the rejection codes, and writes **nothing** under
`shared/`. Add `--sample <path>` for a different file.

---

## 5. Inspect the run

```bash
cd homework-6
ls shared/results/                          # one JSON file per transaction
cat shared/reports/pipeline-summary.md      # the human-readable summary
head -5 shared/audit/audit-log.jsonl        # the audit trail (accounts masked ****NNNN)
```

---

## 6. Run the tests and see the coverage

```bash
cd homework-6
.venv/bin/pytest
```

`pytest.ini` already carries the coverage flags, so this prints the per-module table and writes
`coverage.json`. Expected: **232 passed**, total coverage **99 %** (gate is 80 %, target ≥ 90 %).

Run one file or one edge case:

```bash
.venv/bin/pytest tests/test_fraud_detector.py -v
.venv/bin/pytest -k "ec_11 or ec_13" -v
```

---

## 7. The coverage gate (blocks a push below 80 %)

The gate lives in `scripts/coverage_gate.py` and is wired two ways.

### 7a. As a Claude Code hook

[`.claude/settings.json`](.claude/settings.json) registers a `PreToolUse` hook on `Bash`. It
inspects the command; if it is not a `git push` it exits `0` immediately and stays out of the way.
On a push it runs the suite, reads the total coverage and **exits `2`**, which blocks the tool call
and hands the reason back to the model.

Everything this homework produces lives inside `homework-6/`. Claude Code, however, loads hooks,
slash commands and MCP servers from the **repository root** only. Step 12 below wires the two
together with a single reversible command — nothing outside `homework-6/` is edited until you run
it.

Try the gate by hand (no installation needed):

```bash
# not a push -> silent, exit 0
echo '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' \
  | homework-6/.venv/bin/python homework-6/scripts/coverage_gate.py; echo "exit=$?"

# a push, coverage above the floor -> exit 0
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' \
  | homework-6/.venv/bin/python homework-6/scripts/coverage_gate.py; echo "exit=$?"

# a push with an impossible floor -> blocked, exit 2
echo '{"tool_name":"Bash","tool_input":{"command":"git push"}}' \
  | homework-6/.venv/bin/python homework-6/scripts/coverage_gate.py --threshold 99.9; echo "exit=$?"
```

### 7b. As a git `pre-push` hook

```bash
ln -sf ../../homework-6/scripts/pre-push .git/hooks/pre-push
git push            # runs the same gate; a failure rejects the push
COVERAGE_MIN=90 git push   # raise the floor for one push
```

### 7c. Straight from the command line

```bash
cd homework-6
.venv/bin/python scripts/coverage_gate.py                 # measure and report
.venv/bin/python scripts/coverage_gate.py --threshold 95
.venv/bin/python scripts/coverage_gate.py --simulate-push # force the gate to engage
```

---

## 8. The slash commands (skills)

| Command | What it does |
|---|---|
| `/write-spec <system>` | **Agent 1** — generates a specification following the template (objectives, implementation notes, context, low-level tasks, guardrails, edge cases) |
| `/run-pipeline` | **Agent 2/3** — checks the input, clears `shared/`, runs `integrator.py`, summarises `shared/results/` and reports everything that did not settle |
| `/validate-transactions [path]` | runs the validator in `--dry-run` mode and explains every rejection code |

The files are `homework-6/.claude/commands/*.md`. Run step 12 to expose them at the repository
root, then type `/run-pipeline` in Claude Code.

---

## 9. MCP servers

Both servers are declared in [`mcp.json`](mcp.json). Claude Code reads project MCP servers from the
repository-root `.mcp.json`, so step 12 copies these two entries there:

```json
{
  "mcpServers": {
    "context7":        { "command": "npx",                            "args": ["-y", "@upstash/context7-mcp@latest"] },
    "pipeline-status": { "command": "./homework-6/.venv/bin/python",  "args": ["./homework-6/mcp/server.py"] }
  }
}
```

### 9a. Drive the custom server yourself

```bash
cd homework-6
.venv/bin/python integrator.py --quiet          # make sure there are results to query
.venv/bin/python scripts/verify_mcp_server.py
```

This starts `mcp/server.py` as a **real stdio subprocess**, lists the capabilities, calls
`get_transaction_status` three times (settled / held / unknown id), calls `list_pipeline_results`
and reads `pipeline://summary`. The transcript is committed at
[`docs/sample-run/mcp-interaction.txt`](docs/sample-run/mcp-interaction.txt).

### 9b. From Claude Code

Run step 12, restart Claude Code so it picks up `.mcp.json`, then:

- `/mcp` — `context7` and `pipeline-status` should both be listed as connected;
- ask *"use pipeline-status to show me the status of TXN005"* → the model calls
  `get_transaction_status`;
- context7 is used with `resolve-library-id` followed by `query-docs` — see
  [`research-notes.md`](research-notes.md) for the three lookups made while building this project.

---

## 10. Full verification, end to end

```bash
cd homework-6
.venv/bin/python agents/transaction_validator.py --dry-run     # 1. validation only
.venv/bin/python integrator.py                                 # 2. the pipeline      -> exit 0
.venv/bin/pytest                                               # 3. tests + coverage  -> 232 passed, 99%
.venv/bin/python scripts/coverage_gate.py --simulate-push      # 4. the gate          -> PASSED
.venv/bin/python scripts/verify_mcp_server.py                  # 5. the MCP server    -> all calls OK
```

All five must succeed before the work counts as done.

---

## 12. Wire the hook, the slash commands and the MCP servers into Claude Code

This is the only step that touches anything outside `homework-6/`, it is explicit, and it is
reversible:

```bash
cd homework-6
.venv/bin/python scripts/install_claude_integration.py             # install
.venv/bin/python scripts/install_claude_integration.py --git-hook  # …and the git pre-push hook
.venv/bin/python scripts/install_claude_integration.py --status    # what is wired right now
.venv/bin/python scripts/install_claude_integration.py --uninstall # put the root back
```

It does exactly three things at the repository root, and nothing else:

| Root file | What is added | On uninstall |
|---|---|---|
| `.claude/commands/*.md` | symlinks to `homework-6/.claude/commands/` | symlinks removed, empty dir removed |
| `.claude/settings.json` | the two homework-6 hook entries, each tagged `_homework6_managed` | only the tagged entries removed; a `.pre-homework6` backup is written first if the file already existed |
| `.mcp.json` + `.claude/settings.local.json` | the `context7` and `pipeline-status` server entries | only those two entries removed |

Any pre-existing hook, command or MCP server is left alone — the installer refuses to overwrite a
real file and reports `skip`. Restart Claude Code afterwards so it re-reads `.mcp.json`.

---

## 13. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'fastmcp'` | using the system interpreter instead of `.venv/bin/python`, or `requirements.txt` not installed |
| `ImportError` mentioning `mcp.server` | something put `homework-6/` **ahead** of site-packages on `sys.path`, so the local `mcp/` directory shadows the installed `mcp` package. Run pytest via `.venv/bin/pytest` (not `python -m pytest` from another directory); `tests/conftest.py` normalises this automatically |
| `reconciled=NO` | some message never reached a terminal state — check `shared/quarantine/` and `shared/output/`, and read `shared/audit/audit-log.jsonl` |
| The gate never fires in Claude Code | run step 12, then `/hooks` to confirm the hook is registered; `--status` shows what is wired |
| `/run-pipeline` not offered | run step 12 — without it the commands only exist inside `homework-6/.claude/commands/` |
