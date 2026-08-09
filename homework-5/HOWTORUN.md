# HOWTORUN — Homework 5 (MCP servers)

> **Author / Student Name**: Simon Darienko
> **Homework**: 5 — Configure MCP Servers (GitHub, Filesystem, Jira, Custom FastMCP)

Everything below is executed from the **repository root** unless stated otherwise.

---

## 1. Prerequisites

| Tool | Version used | Needed for |
|---|---|---|
| Python | 3.14.2 (3.10+ is enough) | custom FastMCP server |
| Node.js / npx | 24.x | Filesystem MCP server (`npx`) |
| GitHub CLI (`gh`) | any recent | convenient source of a GitHub token |
| Claude Code | any recent | the MCP client |
| Docker | optional | only for the *local* GitHub MCP alternative |

---

## 2. Install dependencies

```bash
cd homework-5
python3 -m venv .venv
.venv/bin/pip install -r custom-mcp-server/requirements.txt
.venv/bin/python -c "import fastmcp; print(fastmcp.__version__)"   # -> 3.4.6
```

`fastmcp` is the only dependency, declared in
[`custom-mcp-server/requirements.txt`](custom-mcp-server/requirements.txt).

---

## 3. Run the custom MCP server

MCP clients start the server themselves over **stdio**, but you can start it by hand
to confirm the command works:

```bash
# from homework-5/
.venv/bin/python custom-mcp-server/server.py            # stdio (what the client uses)
.venv/bin/python custom-mcp-server/server.py --transport http --port 8765   # optional HTTP mode
```

In stdio mode the process prints its FastMCP banner and then waits for JSON-RPC on
stdin — that silence is the expected, healthy state. Stop it with `Ctrl+C`.

---

## 4. Connect the MCP configuration

The configuration lives in [`homework-5/.mcp.json`](.mcp.json) and an identical copy
sits at the **repository root** (`../.mcp.json`), because Claude Code reads project
MCP servers from `.mcp.json` in the directory it is started in. Keep the two files in
sync:

```bash
# from the repository root
diff .mcp.json homework-5/.mcp.json && echo "in sync"
```

All four servers are declared there:

| Name | Transport | Command / URL |
|---|---|---|
| `github` | http | `https://api.githubcopilot.com/mcp/` + `Authorization: Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}` |
| `filesystem` | stdio | `npx -y @modelcontextprotocol/server-filesystem ./homework-5 ./homework-2` |
| `jira` | http | `https://mcp.atlassian.com/v1/mcp` (OAuth) |
| `lorem-custom` | stdio | `./homework-5/.venv/bin/python ./homework-5/custom-mcp-server/server.py` |

### 4.1 Provide the GitHub token

No token is committed — `.mcp.json` only references `${GITHUB_PERSONAL_ACCESS_TOKEN}`,
which Claude Code expands from the environment:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token)
# or a classic/fine-grained PAT with at least `repo` + `read:org` scopes
```

Export it **before** launching `claude`, e.g. put the line in `~/.zshrc`.

### 4.2 Start the client and approve the servers

```bash
cd /path/to/gen-ai-software-engineering
claude            # answer "Yes" when asked to trust the project's .mcp.json servers
```

Then inside Claude Code:

```text
/mcp              # shows the four servers; use it to authenticate `jira` via OAuth
```

The `jira` entry opens an Atlassian OAuth page in the browser; approve access to your
Atlassian site (`*.atlassian.net`). The other three need no interactive step.

Verify from the shell at any time:

```bash
claude mcp list
```

Expected: `github`, `filesystem`, `jira`, `lorem-custom` — all `✔ Connected`
(before the first approval they are shown as `⏸ Pending approval`).

### 4.3 Alternative: GitHub MCP locally via Docker

If you prefer not to use the remote server, replace the `github` entry with:

```json
"github": {
  "type": "stdio",
  "command": "docker",
  "args": ["run", "-i", "--rm",
           "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
           "ghcr.io/github/github-mcp-server"]
}
```

---

## 5. Use and test the `read` tool

### 5.1 From Claude Code (the intended path)

```text
Use the lorem-custom MCP server: call the read tool with word_count = 12
Read the resource lorem://ipsum/50 from the lorem-custom server
```

Claude calls `mcp__lorem-custom__read` and returns exactly that many words.

### 5.2 From the command line (no client required)

Two scripts open a real MCP session (initialize → `tools/list` → `tools/call`) and
print the transcript:

```bash
cd homework-5

# a) the custom server only — also checks the error path
.venv/bin/python scripts/verify_custom_server.py

# b) every server declared in .mcp.json (reads the same config file)
export GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token)
.venv/bin/python scripts/verify_mcp_servers.py                 # all
.venv/bin/python scripts/verify_mcp_servers.py lorem-custom    # one
```

Expected output for the tool:

```text
tools/call  read(word_count=5)
Lorem ipsum dolor sit amet,
-> word count: 5
```

`jira` is intentionally skipped by the script — it needs the interactive OAuth
handshake, so it is verified from inside Claude Code
(see [`docs/mcp-call-logs/03-jira-mcp.md`](docs/mcp-call-logs/03-jira-mcp.md)).

### 5.3 With the MCP Inspector (optional)

```bash
npx @modelcontextprotocol/inspector \
  homework-5/.venv/bin/python homework-5/custom-mcp-server/server.py
```

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `github` fails with 401 | `GITHUB_PERSONAL_ACCESS_TOKEN` not exported before `claude` started, or the token expired. Re-export and restart the client. |
| `lorem-custom` fails to start | The venv is missing. Re-run step 2; the config points at `./homework-5/.venv/bin/python`. |
| `filesystem` returns "Access denied" | The path is outside the sandbox. The server is limited to `./homework-5` and `./homework-2`; add more roots as extra `args`. |
| Servers stay `⏸ Pending approval` | Project-scoped servers must be trusted once: start `claude` in the repo root and accept, or run `claude mcp reset-project-choices`. |
| Config changes are ignored | Claude Code loads MCP servers at startup — restart the session after editing `.mcp.json`. |
| `word_count exceeds the document length` | `lorem-ipsum.md` holds ~230 words; ask for fewer. |
