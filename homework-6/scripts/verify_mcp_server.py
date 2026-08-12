#!/usr/bin/env python3
"""Exercise the custom MCP server over a real stdio connection and print the transcript.

This is what produces the ``mcp-interaction`` evidence: it starts ``mcp/server.py`` as a
subprocess exactly the way an MCP client would, lists its capabilities, calls both tools and reads
the ``pipeline://summary`` resource.

    python scripts/verify_mcp_server.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from fastmcp import Client  # noqa: E402

SERVER = PROJECT_ROOT / "mcp" / "server.py"
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def rule(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 60 - len(title)))


def payload_of(result):
    if getattr(result, "data", None) is not None:
        return result.data
    return json.loads(result.content[0].text)


async def main() -> int:
    command = str(PYTHON if PYTHON.exists() else sys.executable)
    print(f"$ {command} {SERVER}")
    print("connecting over stdio (MCP JSON-RPC)...")

    from fastmcp.client.transports import StdioTransport

    transport = StdioTransport(command=command, args=[str(SERVER)])
    async with Client(transport) as client:
        rule("initialize / capabilities")
        tools = await client.list_tools()
        resources = await client.list_resources()
        for tool in tools:
            print(f"  tool     : {tool.name}{_signature(tool)}")
        for resource in resources:
            print(f"  resource : {resource.uri}")

        rule("tools/call get_transaction_status TXN001")
        print(json.dumps(payload_of(await client.call_tool(
            "get_transaction_status", {"transaction_id": "TXN001"}
        )), indent=2))

        rule("tools/call get_transaction_status TXN005 (held)")
        print(json.dumps(payload_of(await client.call_tool(
            "get_transaction_status", {"transaction_id": "TXN005"}
        )), indent=2))

        rule("tools/call get_transaction_status TXN999 (unknown)")
        print(json.dumps(payload_of(await client.call_tool(
            "get_transaction_status", {"transaction_id": "TXN999"}
        )), indent=2))

        rule("tools/call list_pipeline_results")
        listing = payload_of(await client.call_tool("list_pipeline_results"))
        print(json.dumps({"total": listing["total"], "by_status": listing["by_status"]}, indent=2))
        for item in listing["transactions"]:
            print(
                f"  {item['transaction_id']:<8}{item['status']:<10}"
                f"{item['amount']:>10} {item['currency']}  risk={item['risk_score']}"
            )

        rule("resources/read pipeline://summary")
        contents = await client.read_resource("pipeline://summary")
        print("\n".join(contents[0].text.splitlines()[:18]))
        print("  ... (truncated)")

    print("\nAll MCP calls completed successfully.")
    return 0


def _signature(tool) -> str:
    properties = (tool.inputSchema or {}).get("properties") or {}
    return "(" + ", ".join(properties) + ")"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
