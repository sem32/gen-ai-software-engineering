# Screenshots

Two sets of screenshots belong here.

## A. AI workflow — present ✅

How the homework itself was produced with Claude Code (Opus 5): the prompt, the
clarification round, the files being written, the MCP calls being made and the final
report.

| File | What it shows |
|---|---|
| `workflow-1-task-start-and-clarifications.png` | The prompt *"сделай домашнее задание #5 согласно описанию в homework-5/TASKS.md"* and the three clarifying questions the agent asked (screenshots strategy, Jira project, masking of internal ticket keys) |
| `workflow-2-custom-server-created.png` | `lorem-ipsum.md` and the FastMCP `server.py` being written |
| `workflow-3-requirements-and-verification-script.png` | `requirements.txt` with `fastmcp>=3.4.6`, the stdio verification script, and the start of `.mcp.json` |
| `workflow-4-mcp-config-and-jira-call.png` | The `github` entry of `.mcp.json` with `${GITHUB_PERSONAL_ACCESS_TOKEN}`, `verify_mcp_servers.py`, and the **Atlassian MCP call** for the last 5 WMS bugs |
| `workflow-5-documentation-written.png` | `HOWTORUN.md` and `README.md` being generated |
| `workflow-6-mcp-list-and-readme-fixes.png` | The real `claude mcp list` output with all four servers, and the correction of the README once `jira` turned out to need its own OAuth login |
| `workflow-7-final-summary.png` | The agent's final report: what each of the four servers returned |

## B. MCP call results — present ✅

One screenshot per server, each showing the MCP tool that was invoked, its arguments
and the value that came back. Captured from **headless Claude Code runs**
(`claude -p "…"`) against the servers declared in `.mcp.json`, so every call is a real
one; the same calls are also stored as text in [`../mcp-call-logs/`](../mcp-call-logs/).

| File | Server | Call shown |
|---|---|---|
| `github-mcp-result.png` | `github` | `list_pull_requests` + `list_commits` on `sem32/gen-ai-software-engineering` |
| `filesystem-mcp-result.png` | `filesystem` | `list_allowed_directories`, `list_directory`, `directory_tree` |
| `jira-or-notion-mcp-result.png` | `jira` | `searchJiraIssuesUsingJql` — the last 5 WMS bugs (keys masked) |
| `custom-mcp-read-tool-result.png` | `lorem-custom` | `read(word_count=12)`, `read()` with the default, and the resource `lorem://ipsum/30` |

Two caveats worth stating:

- The **Jira** shot goes through the already-authenticated Atlassian connector instead
  of the project-scoped `jira` entry — a headless run cannot complete the OAuth
  handshake. It is the same `https://mcp.atlassian.com/v1/mcp` endpoint either way.
- The **filesystem** shot is what revealed that the client's MCP *roots* override the
  server's command-line directories: it reports the repository root. That finding is
  documented in the Task 2 section of the homework README.

### Reproducing them

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token)
cd /path/to/gen-ai-software-engineering

claude -p "Using the github MCP server, call list_pull_requests and list_commits for owner sem32, repo gen-ai-software-engineering, perPage 5."
claude -p "Using the filesystem MCP server, call list_allowed_directories, then list_directory on homework-5, then directory_tree on homework-5/custom-mcp-server."
claude -p "Give me the tickets of the last 5 bugs on the WMS project"
claude -p "Using the lorem-custom MCP server: call the read tool with word_count = 12, then with no arguments, then read the resource lorem://ipsum/30."
```

Inside an interactive session the same prompts work after `/mcp` (approve the project
servers and complete the Atlassian OAuth login); `ctrl+o` expands the tool-call blocks
so request and response are both in frame.

## Privacy

The Jira screenshot comes from a private corporate Jira, so it shows only ticket
keys, type, priority, status and creation date — no summaries, descriptions,
assignees or customer data — and the keys themselves are masked as `WMS-273XX`. The
committed Markdown transcript
([`../mcp-call-logs/03-jira-mcp.md`](../mcp-call-logs/03-jira-mcp.md)) masks them the
same way; the unmasked version stays local in a git-ignored `*.local.md` file.
