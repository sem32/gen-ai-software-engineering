"""Verify the custom MCP server over a real stdio MCP session.

Spawns ``custom-mcp-server/server.py`` exactly the way an MCP client would,
performs the initialize handshake, then lists and exercises its capabilities.

    python scripts/verify_custom_server.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "custom-mcp-server" / "server.py"


def show(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


async def main() -> int:
    transport = StdioTransport(command=sys.executable, args=[str(SERVER)])

    async with Client(transport) as client:
        show("tools/list")
        for tool in await client.list_tools():
            print(f"- {tool.name}: {tool.description.splitlines()[0]}")
            print(f"  input schema: {tool.inputSchema}")

        show("resources/list")
        for res in await client.list_resources():
            print(f"- {res.uri} ({res.mimeType}): {res.description}")

        show("resources/templates/list")
        for tpl in await client.list_resource_templates():
            print(f"- {tpl.uriTemplate} ({tpl.mimeType}): {tpl.description}")

        show("resources/read  lorem://ipsum   (default word_count = 30)")
        content = await client.read_resource("lorem://ipsum")
        text = content[0].text
        print(text)
        print(f"\n-> word count: {len(text.split())}")

        show("resources/read  lorem://ipsum/10")
        content = await client.read_resource("lorem://ipsum/10")
        text = content[0].text
        print(text)
        print(f"\n-> word count: {len(text.split())}")

        show("tools/call  read()   (no arguments -> default 30)")
        result = await client.call_tool("read", {})
        print(result.content[0].text)
        print(f"\n-> word count: {len(result.content[0].text.split())}")

        show("tools/call  read(word_count=5)")
        result = await client.call_tool("read", {"word_count": 5})
        print(result.content[0].text)
        print(f"\n-> word count: {len(result.content[0].text.split())}")

        show("tools/call  read(word_count=0)   (expected: error)")
        try:
            await client.call_tool("read", {"word_count": 0})
        except Exception as exc:  # noqa: BLE001 - we want the client-visible message
            print(f"error (as expected): {exc}")
        else:
            print("FAILED: no error raised")
            return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
