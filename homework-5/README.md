# Homework 5 — MCP Server Configuration

> **Author / Student Name**: Simon Darienko
> **Homework**: 5 — Configure MCP Servers (GitHub, Filesystem, Jira, Custom)
> **AI Tools Used**: Claude Code (Opus 5) as the MCP client
> **Run instructions**: [HOWTORUN.md](HOWTORUN.md)

Four MCP servers are registered for this repository — three external ones (GitHub,
Filesystem, Jira) and one written from scratch with **FastMCP**. Every server was
exercised with real MCP calls; the transcripts live in
[`docs/mcp-call-logs/`](docs/mcp-call-logs/) and the screenshots in
[`docs/screenshots/`](docs/screenshots/).

## What is MCP, in two lines

The **Model Context Protocol** lets an AI client (Claude Code, Copilot, …) talk to
external systems through a uniform JSON-RPC interface. A server advertises its
capabilities during the `initialize` handshake, and the client then discovers them
with `tools/list` / `resources/list` and invokes them with `tools/call` /
`resources/read`.

| Concept | Meaning | Example here |
|---|---|---|
| **Resource** | A **URI Claude can read from** — a passive piece of context (file, API response, database row). The client decides when to read it; reading must have no side effects. | `lorem://ipsum`, `lorem://ipsum/{word_count}` |
| **Tool** | An **action Claude can call** to perform an operation (read a file, run a command, create an issue). The model chooses to invoke it and passes arguments described by a JSON schema. | `read(word_count=30)`, `list_pull_requests(...)` |

## The four servers

| # | Server | Transport | What it is | Task |
|---|---|---|---|---|
| 1 | `github` | HTTP | Official remote GitHub MCP server, `https://api.githubcopilot.com/mcp/`, 44 tools | Task 1 |
| 2 | `filesystem` | stdio | `@modelcontextprotocol/server-filesystem` via `npx`, sandboxed to `./homework-5` and `./homework-2`, 14 tools | Task 2 |
| 3 | `jira` | HTTP | Atlassian remote MCP server, `https://mcp.atlassian.com/v1/mcp` (OAuth to `wildix.atlassian.net`) | Task 3 |
| 4 | `lorem-custom` | stdio | Own FastMCP server, `custom-mcp-server/server.py` — 1 tool, 1 resource, 1 resource template | Task 4 |

Configuration: [`.mcp.json`](.mcp.json) (an identical copy sits at the repository
root, which is where Claude Code loads project MCP servers from).
**No credentials are committed** — the GitHub entry references
`${GITHUB_PERSONAL_ACCESS_TOKEN}`, which the client expands from the environment,
and Jira uses OAuth.

```bash
$ export GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token)
$ claude mcp list
github: https://api.githubcopilot.com/mcp/ (HTTP) - ✔ Connected
filesystem: npx -y @modelcontextprotocol/server-filesystem ./homework-5 ./homework-2 - ✔ Connected
jira: https://mcp.atlassian.com/v1/mcp (HTTP) - ! Needs authentication
lorem-custom: ./homework-5/.venv/bin/python ./homework-5/custom-mcp-server/server.py - ✔ Connected
```

`jira` is an OAuth server: the project-scoped entry turns green only after a one-time
browser login started with `/mcp` inside Claude Code. The Jira calls of Task 3 were
made against **the same endpoint** (`https://mcp.atlassian.com/v1/mcp`) through the
already-authenticated Atlassian connector of this Claude Code session.

---

## Task 1 — GitHub MCP

Registered as a remote HTTP server authenticated with a GitHub PAT (taken from
`gh auth token`). Interactions performed against
`sem32/gen-ai-software-engineering`:

- `get_me` → account `sem32` (Simon Darienko)
- `list_pull_requests(state=all, perPage=5)` → PR #3 *"Add Claude Code GitHub Workflow"* (open), …
- `list_commits(perPage=5)` → `de9b4fc Add recommended agents, skills, and pipelines`, `763118e Homework 5,6 added`, …

Transcript: [`docs/mcp-call-logs/01-github-mcp.md`](docs/mcp-call-logs/01-github-mcp.md) ·
Screenshots: [`workflow-4`](docs/screenshots/workflow-4-mcp-config-and-jira-call.png) (config), [`workflow-6`](docs/screenshots/workflow-6-mcp-list-and-readme-fixes.png) (`claude mcp list`) · in-client call result: `docs/screenshots/github-mcp-result.png` ⏳

## Task 2 — Filesystem MCP

Registered over stdio with two allowed roots, so the server can never touch
anything outside the homework folders:

```text
tools/call list_allowed_directories
Allowed directories:
/Users/sem/git/education/gen-ai-software-engineering/homework-5
/Users/sem/git/education/gen-ai-software-engineering/homework-2
```

Interactions: `list_directory(homework-5)`, `read_text_file(requirements.txt)`,
`directory_tree(custom-mcp-server)`.

Transcript: [`docs/mcp-call-logs/02-filesystem-mcp.md`](docs/mcp-call-logs/02-filesystem-mcp.md) ·
Screenshots: [`workflow-6`](docs/screenshots/workflow-6-mcp-list-and-readme-fixes.png) (`claude mcp list`) · in-client call result: `docs/screenshots/filesystem-mcp-result.png` ⏳

## Task 3 — Jira MCP

Prompt: *"Give me the tickets of the last 5 bugs on a project"*. The model resolved
the Atlassian site, listed the visible projects and queried the **WMS** project:

```text
searchJiraIssuesUsingJql
  jql = "project = WMS AND issuetype = Bug ORDER BY created DESC"
  fields = [status, issuetype, priority, created, resolution]
  maxResults = 5
```

Five bug tickets were returned (`WMS-273XX`, two of 2026-08-07 and …). **Ticket keys
are masked in the committed documentation**: the source is a private corporate Jira
and this repository is public. Only ticket numbers, type, priority, status and
creation date are reproduced — no summaries, descriptions, assignees or customer
data. The unmasked transcript stays local in a git-ignored `*.local.md` file.

Transcript: [`docs/mcp-call-logs/03-jira-mcp.md`](docs/mcp-call-logs/03-jira-mcp.md) ·
Screenshot: [`workflow-4`](docs/screenshots/workflow-4-mcp-config-and-jira-call.png) (the Atlassian call being made) · in-client call result: `docs/screenshots/jira-or-notion-mcp-result.png` ⏳

## Task 4 — Custom MCP server (FastMCP)

[`custom-mcp-server/server.py`](custom-mcp-server/server.py) serves word-limited
excerpts of [`custom-mcp-server/lorem-ipsum.md`](custom-mcp-server/lorem-ipsum.md)
(224 words, Markdown headings excluded).

| Kind | Identifier | Behaviour |
|---|---|---|
| Resource | `lorem://ipsum` | first **30** words (the default) |
| Resource template | `lorem://ipsum/{word_count}` | first `word_count` words |
| Tool | `read(word_count: int = 30)` | same content, callable by the model |

```python
@mcp.resource("lorem://ipsum/{word_count}", mime_type="text/plain")
def lorem_words(word_count: int) -> str:
    return _read_words(word_count)

@mcp.tool
def read(word_count: int = DEFAULT_WORD_COUNT) -> str:
    """Read the lorem-ipsum document."""
    return _read_words(word_count)
```

A non-positive `word_count`, or one larger than the document, raises an explicit
error instead of silently returning something else:

```text
tools/call read(word_count=0)
error (as expected): Error calling tool 'read': word_count must be a positive integer
```

Dependency: `fastmcp>=3.4.6` in
[`custom-mcp-server/requirements.txt`](custom-mcp-server/requirements.txt).

Transcript: [`docs/mcp-call-logs/04-custom-mcp.md`](docs/mcp-call-logs/04-custom-mcp.md) ·
Screenshots: [`workflow-2`](docs/screenshots/workflow-2-custom-server-created.png), [`workflow-3`](docs/screenshots/workflow-3-requirements-and-verification-script.png) · in-client call result: `docs/screenshots/custom-mcp-read-tool-result.png` ⏳

---

## How AI was used

The whole homework was produced in one Claude Code session (Opus 5), which acted both
as the *author* of the code and as the *MCP client* under test. The session is
documented shot by shot in
[`docs/screenshots/`](docs/screenshots/README.md):

| Step | What the agent did | Screenshot |
|---|---|---|
| 1 | Read `TASKS.md`, inspected the repo conventions, then **asked three clarifying questions** instead of guessing: how to produce screenshots, which Jira project to query, and whether internal ticket keys may be committed to a public repo | [`workflow-1`](docs/screenshots/workflow-1-task-start-and-clarifications.png) |
| 2 | Wrote `lorem-ipsum.md` and the FastMCP `server.py` (resource + `read` tool) | [`workflow-2`](docs/screenshots/workflow-2-custom-server-created.png) |
| 3 | Pinned `fastmcp>=3.4.6` and wrote a stdio verification client — the server was tested through a real MCP handshake, not by eyeballing the code | [`workflow-3`](docs/screenshots/workflow-3-requirements-and-verification-script.png) |
| 4 | Wrote `.mcp.json` with `${GITHUB_PERSONAL_ACCESS_TOKEN}` instead of a literal token, and ran the Jira query for the last 5 WMS bugs over the Atlassian MCP server | [`workflow-4`](docs/screenshots/workflow-4-mcp-config-and-jira-call.png) |
| 5 | Generated `HOWTORUN.md` and `README.md` | [`workflow-5`](docs/screenshots/workflow-5-documentation-written.png) |
| 6 | Ran `claude mcp list`, found that `jira` reported *Needs authentication*, and **corrected the README** it had just written rather than leaving the optimistic claim in place | [`workflow-6`](docs/screenshots/workflow-6-mcp-list-and-readme-fixes.png) |
| 7 | Final report: what each of the four servers returned, and what was left for the human | [`workflow-7`](docs/screenshots/workflow-7-final-summary.png) |

What was decided by the human, not the model: the Jira project (WMS), masking of the
internal ticket keys, and taking the screenshots. What was verified by execution
rather than trusted: every MCP call in this README.

> ⏳ **Still open** — `TASKS.md` also asks for one screenshot of an MCP *call result*
> per server taken inside the client (`github-mcp-result.png`,
> `filesystem-mcp-result.png`, `jira-or-notion-mcp-result.png`,
> `custom-mcp-read-tool-result.png`). Those four are not captured yet; the equivalent
> evidence is currently the command-line transcripts in
> [`docs/mcp-call-logs/`](docs/mcp-call-logs/). The exact prompts to reproduce them
> are listed in [`docs/screenshots/README.md`](docs/screenshots/README.md).

## Verification

Two scripts open real MCP sessions instead of trusting the config by eye. The second
one **reads `.mcp.json` itself**, so it proves the committed configuration is valid
and points at the right servers:

```bash
cd homework-5
.venv/bin/python scripts/verify_custom_server.py                 # custom server + error path
export GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token)
.venv/bin/python scripts/verify_mcp_servers.py                   # github, filesystem, lorem-custom
```

Results at the time of submission:

| Check | Result |
|---|---|
| `fastmcp` importable, version | ✅ 3.4.6 |
| Custom server starts over stdio | ✅ handshake completed |
| `lorem://ipsum` returns 30 words | ✅ counted 30 |
| `lorem://ipsum/10` returns 10 words | ✅ counted 10 |
| `read()` / `read(word_count=5)` | ✅ 30 / 5 words |
| `read(word_count=0)` | ✅ rejected with a clear error |
| `.mcp.json` parses and all stdio/HTTP entries connect | ✅ 3/3 non-OAuth servers |
| GitHub MCP authenticated call | ✅ `get_me` → `sem32` |
| Filesystem MCP sandboxed call | ✅ 2 allowed roots |
| Jira MCP JQL call | ✅ 5 WMS bugs returned |
| `claude mcp list` registration | ✅ all 4 listed; 3 `Connected`, `jira` pending its one-time OAuth login |

## Project structure

```text
homework-5/
├── README.md                        # this file
├── HOWTORUN.md                      # install, run, connect, test
├── TASKS.md                         # assignment
├── .mcp.json                        # all four servers (copy at repo root)
├── .gitignore                       # .venv, unmasked *.local.md transcripts
├── custom-mcp-server/
│   ├── server.py                    # FastMCP server: resource + `read` tool
│   ├── lorem-ipsum.md               # source text (224 words)
│   └── requirements.txt             # fastmcp>=3.4.6
├── scripts/
│   ├── verify_custom_server.py      # stdio session against the custom server
│   └── verify_mcp_servers.py        # drives every server declared in .mcp.json
└── docs/
    ├── mcp-call-logs/               # captured request/response transcripts
    │   ├── 01-github-mcp.md
    │   ├── 02-filesystem-mcp.md
    │   ├── 03-jira-mcp.md
    │   └── 04-custom-mcp.md
    └── screenshots/
        ├── README.md                 # what each shot shows / what is still missing
        └── workflow-1…7-*.png        # the AI session that produced this homework
```

## Security notes

- No secret is committed: the GitHub token is injected via `${GITHUB_PERSONAL_ACCESS_TOKEN}`, Jira uses OAuth.
- The Filesystem server is restricted to two homework directories.
- The GitHub `get_me` transcript has the account e-mail redacted.
- Jira ticket keys are masked in everything that is committed.
