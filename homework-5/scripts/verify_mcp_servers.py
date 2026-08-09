"""Verify the MCP servers declared in ``homework-5/.mcp.json``.

Reads the very same configuration file the MCP client uses, expands
``${ENV_VAR}`` placeholders, then opens a real MCP session against each stdio /
HTTP server and exercises it. The transcripts are the evidence stored in
``docs/mcp-call-logs/``.

    export GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token)
    python scripts/verify_mcp_servers.py [github|filesystem|lorem-custom]

The ``jira`` entry is not exercised here: the Atlassian server uses an
interactive OAuth handshake, so it is verified from inside Claude Code
(see docs/mcp-call-logs/03-jira-mcp.md).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

HOMEWORK_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = HOMEWORK_DIR.parent
CONFIG = HOMEWORK_DIR / ".mcp.json"

ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def expand(value: str) -> str:
    """Substitute ``${VAR}`` placeholders from the environment."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = os.environ.get(name)
        if not resolved:
            raise SystemExit(f"Environment variable {name} is not set")
        return resolved

    return ENV_PATTERN.sub(replace, value)


def load_servers() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))["mcpServers"]


def make_client(name: str, spec: dict) -> Client:
    """Build a client for one .mcp.json entry, mirroring the client's own rules."""
    if spec.get("type") == "http":
        headers = {k: expand(v) for k, v in spec.get("headers", {}).items()}
        return Client(StreamableHttpTransport(url=spec["url"], headers=headers))

    # stdio: relative commands/paths resolve against the repository root,
    # which is the working directory the MCP client starts the server in.
    return Client(
        StdioTransport(
            command=spec["command"],
            args=spec["args"],
            cwd=str(REPO_ROOT),
        )
    )


def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def text_of(result) -> str:
    return "\n".join(block.text for block in result.content if hasattr(block, "text"))


async def verify_github(client: Client) -> None:
    tools = await client.list_tools()
    banner(f"github :: tools/list  ({len(tools)} tools)")
    print(", ".join(sorted(t.name for t in tools)[:25]) + " ...")

    banner("github :: tools/call  get_me")
    print(text_of(await client.call_tool("get_me", {}))[:600])

    banner("github :: tools/call  list_pull_requests(sem32/gen-ai-software-engineering)")
    result = await client.call_tool(
        "list_pull_requests",
        {"owner": "sem32", "repo": "gen-ai-software-engineering", "state": "all", "perPage": 5},
    )
    print(text_of(result)[:2000])

    banner("github :: tools/call  list_commits(sem32/gen-ai-software-engineering)")
    result = await client.call_tool(
        "list_commits",
        {"owner": "sem32", "repo": "gen-ai-software-engineering", "perPage": 5},
    )
    print(text_of(result)[:2000])


async def verify_filesystem(client: Client) -> None:
    tools = await client.list_tools()
    banner(f"filesystem :: tools/list  ({len(tools)} tools)")
    print(", ".join(sorted(t.name for t in tools)))

    banner("filesystem :: tools/call  list_allowed_directories")
    print(text_of(await client.call_tool("list_allowed_directories", {})))

    banner("filesystem :: tools/call  list_directory(homework-5)")
    print(text_of(await client.call_tool("list_directory", {"path": str(HOMEWORK_DIR)})))

    banner("filesystem :: tools/call  read_text_file(custom-mcp-server/requirements.txt)")
    result = await client.call_tool(
        "read_text_file",
        {"path": str(HOMEWORK_DIR / "custom-mcp-server" / "requirements.txt")},
    )
    print(text_of(result))

    banner("filesystem :: tools/call  directory_tree(custom-mcp-server)")
    result = await client.call_tool(
        "directory_tree", {"path": str(HOMEWORK_DIR / "custom-mcp-server")}
    )
    print(text_of(result)[:1500])


async def verify_lorem(client: Client) -> None:
    tools = await client.list_tools()
    banner(f"lorem-custom :: tools/list  ({len(tools)} tools)")
    for tool in tools:
        print(f"- {tool.name}: {tool.description.splitlines()[0]}")
        print(f"  input schema: {json.dumps(tool.inputSchema)}")

    banner("lorem-custom :: resources/list")
    for res in await client.list_resources():
        print(f"- {res.uri} ({res.mimeType}): {res.description}")

    banner("lorem-custom :: resources/templates/list")
    for tpl in await client.list_resource_templates():
        print(f"- {tpl.uriTemplate} ({tpl.mimeType}): {tpl.description}")

    banner("lorem-custom :: resources/read  lorem://ipsum   (default word_count = 30)")
    content = await client.read_resource("lorem://ipsum")
    print(content[0].text)
    print(f"\n-> word count: {len(content[0].text.split())}")

    banner("lorem-custom :: resources/read  lorem://ipsum/10")
    content = await client.read_resource("lorem://ipsum/10")
    print(content[0].text)
    print(f"\n-> word count: {len(content[0].text.split())}")

    banner("lorem-custom :: tools/call  read()   (no arguments -> default 30)")
    result = await client.call_tool("read", {})
    print(text_of(result))
    print(f"\n-> word count: {len(text_of(result).split())}")

    banner("lorem-custom :: tools/call  read(word_count=5)")
    result = await client.call_tool("read", {"word_count": 5})
    print(text_of(result))
    print(f"\n-> word count: {len(text_of(result).split())}")


VERIFIERS = {
    "github": verify_github,
    "filesystem": verify_filesystem,
    "lorem-custom": verify_lorem,
}


async def main(names: list[str]) -> int:
    servers = load_servers()
    for name in names:
        if name not in servers:
            raise SystemExit(f"{name} is not declared in {CONFIG}")
        print(f"\n### {name}  <-  {json.dumps(servers[name])}")
        async with make_client(name, servers[name]) as client:
            await VERIFIERS[name](client)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    requested = sys.argv[1:] or list(VERIFIERS)
    raise SystemExit(asyncio.run(main(requested)))
