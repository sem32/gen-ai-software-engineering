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

## B. MCP call results — still to capture ⏳

`TASKS.md` asks for a screenshot of an MCP **call result** per server, taken in a
Claude Code session. Those four are not captured yet. The command-line transcripts in
[`../mcp-call-logs/`](../mcp-call-logs/) already prove the same calls, but the
screenshots are an explicit deliverable.

### Before you start

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token)
cd /path/to/gen-ai-software-engineering
claude
```

Inside the session run `/mcp` once: approve the project servers and complete the
Atlassian OAuth login for `jira`. A screenshot of that `/mcp` panel listing the four
servers is a useful extra (`mcp-servers-list.png`).

### The four shots

| File | Prompt to type | What must be visible |
|---|---|---|
| `github-mcp-result.png` | `Using the github MCP server, list the last 5 pull requests and the last 5 commits of sem32/gen-ai-software-engineering` | the `github - list_pull_requests` / `list_commits` tool calls and their results |
| `filesystem-mcp-result.png` | `Using the filesystem MCP server, show the allowed directories and the tree of homework-5/custom-mcp-server` | the `filesystem - list_allowed_directories` / `directory_tree` calls and their output |
| `jira-or-notion-mcp-result.png` | `Give me the tickets of the last 5 bugs on the WMS project` | the `jira - searchJiraIssuesUsingJql` call with the JQL, plus the five returned bug keys |
| `custom-mcp-read-tool-result.png` | `Using the lorem-custom MCP server, call the read tool with word_count = 12, then read the resource lorem://ipsum/30` | the `lorem-custom - read` tool call, its arguments and the returned words |

Expand the tool-call blocks (`ctrl+o` toggles full output in Claude Code) so both the
request and the response are visible in the frame.

## Privacy

The Jira screenshot comes from a private corporate Jira. Before committing it, crop
or blur everything except the ticket keys, type, status and dates — no summaries,
descriptions, assignees or customer data. The committed Markdown transcript
([`../mcp-call-logs/03-jira-mcp.md`](../mcp-call-logs/03-jira-mcp.md)) masks the keys
as well.
