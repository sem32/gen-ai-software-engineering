# HOWTORUN — Homework 6 capstone

> **Author / Student**: Simon Darienko
> Every command below is run from the repository root unless the step says otherwise.
> Times are from a MacBook (Python 3.14.2): full pipeline run ≈ 0.2 s, full test suite ≈ 33 s,
> `./demo.sh` ≈ 1 min.

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
3. The five message-driven agents each drain their inbox once, in order (the sixth, `reporting_agent`, aggregates at the end).
4. The reporting agent writes `shared/reports/pipeline-summary.{json,md}`.
5. A results table is printed and the run reconciles input count against terminal count.

Expected tail of the output — **8 processed, 5 settled, 1 held, 2 rejected, `reconciled=yes`**, exit
code `0`. A committed copy of a real run is in [`docs/sample-run/`](docs/sample-run/).

Useful flags:

```bash
.venv/bin/python integrator.py --rules policy-strict         # a different policy rule pack
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
`coverage.json`. Expected: **442 passed**, total coverage **93 %** (gate is 80 %, target ≥ 90 %).

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
slash commands and MCP servers from the **repository root** only. Step 16 below wires the two
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

The files are `homework-6/.claude/commands/*.md`. Run step 16 to expose them at the repository
root, then type `/run-pipeline` in Claude Code.

---

## 9. MCP servers

Both servers are declared in [`mcp.json`](mcp.json). Claude Code reads project MCP servers from the
repository-root `.mcp.json`, so step 16 copies these two entries there:

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

Run step 16, restart Claude Code so it picks up `.mcp.json`, then:

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
.venv/bin/pytest                                               # 3. tests + coverage  -> 442 passed, 93%
.venv/bin/python scripts/coverage_gate.py --simulate-push      # 4. the gate          -> PASSED
.venv/bin/python scripts/verify_mcp_server.py                  # 5. the MCP server    -> all calls OK
.venv/bin/python integrator.py --rules policy-strict --quiet   # 6. the strict pack   -> exit 0
./demo.sh                                                      # 7. everything        -> exit 0
```

All seven must succeed before the work counts as done. Step 7 subsumes the rest and is the one a
reviewer should run first.

---

## 12. The one-command demo

```bash
cd homework-6
./demo.sh                    # everything: 8 steps, zero manual input
./demo.sh --no-tests         # skip the slow step
./demo.sh --keep-running     # leave the mesh and gateway up, print their URLs
./demo.sh --base-port 8801   # pin the agent service ports
```

It provisions the virtualenv if needed, runs the validation dry-run, a default-pack pipeline run, the
same input under `policy-strict` **with a printed diff of what changed**, starts one HTTP service per
agent plus the gateway on free ports, submits transactions over HTTP and shows the hop-by-hop trace,
runs the suite and the coverage gate, exercises the MCP server, then stops everything through a `trap`
that also fires on failure and `Ctrl-C`. It exits non-zero on the first failing step and names it. The
transcript lands in [`docs/sample-run/demo.log`](docs/sample-run/demo.log).

---

## 13. The interactive presentation

[`docs/presentation.html`](docs/presentation.html) is a self-contained deck that **runs the demo from
the page** and animates the real chain. Two ways to open it:

```bash
# 1. served by the API — same origin, connects by itself, nothing to configure
./demo.sh --keep-running          # then open the printed gateway URL, e.g. http://127.0.0.1:52341/

# 2. or start the stack by hand
.venv/bin/python -m services --base-port 8801 &
HW6_SERVICE_BASE_PORT=8801 .venv/bin/python -m gateway --port 8080 --transport rest &
open http://127.0.0.1:8080/
```

Opening the file directly (`open docs/presentation.html`) also works: the page then runs in **offline
mode**, replaying recorded responses, and tells you how to get live data. Put a reachable API base in
the field and press *Connect* to switch to live.

The buttons submit real transactions — settled, held, rejected, a schema violation, and the same
9 999.99 under both rule packs. The hop order and every status come from the response's `trace`; only
the pacing between hops is presentational.

---

## 14. The agent service mesh

```bash
cd homework-6
.venv/bin/python -m services --print-topology         # who talks to whom, as JSON
.venv/bin/python -m services --base-port 8801         # one process per agent
curl -s localhost:8801/health | python3 -m json.tool  # each service names its successor
```

Drive the chain directly, without the gateway — this is the CR-02 architecture in one command:

```bash
curl -s -X POST localhost:8801/process -H 'Content-Type: application/json' -d '{
  "message_id":"demo-1","timestamp":"2026-03-16T09:00:00Z","source_agent":"curl",
  "target_agent":"transaction_validator","message_type":"transaction",
  "data":{"transaction_id":"CLI001","timestamp":"2026-03-16T09:00:00Z",
          "source_account":"ACC-1001","destination_account":"ACC-2001","amount":"1500.00",
          "currency":"USD","transaction_type":"transfer","metadata":{"channel":"api","country":"US"}}}'
```

The response carries the terminal outcome plus the `trace` of every hop. Replay the identical body and
the first service answers from its idempotency cache (`idempotent_replay: true`) without writing a
second result.

---

## 15. Rule packs — behaviour without code changes

```bash
.venv/bin/python integrator.py --rules policy-strict     # §8b: 3 settled / 3 held, one changed fee
curl -s 'localhost:8080/rules?rules=policy-strict'       # the pack, as loaded
curl -s -X POST 'localhost:8080/transactions?rules=policy-strict' -d '{...}'   # per request
HW6_POLICY_RULES=policy-strict .venv/bin/python integrator.py                  # per environment
```

Schema, operators, facts and the conflict rules: [`rules/README.md`](rules/README.md).

---

## 16. Wire the hook, the slash commands and the MCP servers into Claude Code

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

## 17. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'fastmcp'` | using the system interpreter instead of `.venv/bin/python`, or `requirements.txt` not installed |
| `ImportError` mentioning `mcp.server` | something put `homework-6/` **ahead** of site-packages on `sys.path`, so the local `mcp/` directory shadows the installed `mcp` package. Run pytest via `.venv/bin/pytest` (not `python -m pytest` from another directory); `tests/conftest.py` normalises this automatically |
| `reconciled=NO` | some message never reached a terminal state — check `shared/quarantine/` and `shared/output/`, and read `shared/audit/audit-log.jsonl` |
| The gate never fires in Claude Code | run step 16, then `/hooks` to confirm the hook is registered; `--status` shows what is wired |
| `/run-pipeline` not offered | run step 16 — without it the commands only exist inside `homework-6/.claude/commands/` |
| `port N is already in use` from the mesh | pass `--base-port` a free block of five ports, or let `demo.sh` pick one |
| The presentation says **offline** | it found no API at that address. Run `./demo.sh --keep-running` and open the printed URL, or paste a reachable base and press *Connect* |
| `503 upstream_unavailable` | a mid-chain agent service is down. `curl <service>/health` for each; the journal records the failed hop as `forward_failed` |
