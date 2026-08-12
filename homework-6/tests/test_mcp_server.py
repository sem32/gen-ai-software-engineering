"""Tests for the custom FastMCP server (spec task T-7).

The server is exercised over FastMCP's in-memory transport — the real MCP protocol, no network,
no subprocess (see ``research-notes.md``, query 1).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json

import pytest

from agents import results_store
from conftest import ROOT

pytest.importorskip("fastmcp")
from fastmcp import Client  # noqa: E402

SERVER_PATH = ROOT / "mcp" / "server.py"


@pytest.fixture(scope="module")
def server_module():
    # Loaded under a non-conflicting module name: the directory is called `mcp`, and importing it
    # as such would shadow the package FastMCP itself depends on.
    spec = importlib.util.spec_from_file_location("pipeline_mcp_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def server(server_module, completed_run, monkeypatch):
    """The server bound to an isolated, freshly-run workspace."""
    monkeypatch.setattr(results_store, "DEFAULT_SHARED_ROOT", completed_run.shared)
    return server_module.mcp


def call(server, tool_name, arguments=None):
    async def _run():
        async with Client(server) as client:
            return await client.call_tool(tool_name, arguments or {})

    result = asyncio.run(_run())
    if getattr(result, "data", None) is not None:
        return result.data
    return json.loads(result.content[0].text)


def read_resource(server, uri):
    async def _run():
        async with Client(server) as client:
            return await client.read_resource(uri)

    return asyncio.run(_run())[0].text


# --------------------------------------------------------------------------------------


def test_server_advertises_the_required_capabilities(server):
    async def _run():
        async with Client(server) as client:
            tools = await client.list_tools()
            resources = await client.list_resources()
            return {tool.name for tool in tools}, {str(res.uri) for res in resources}

    tool_names, resource_uris = asyncio.run(_run())
    assert {"get_transaction_status", "list_pipeline_results"} <= tool_names
    assert "pipeline://summary" in resource_uris


def test_get_transaction_status_returns_a_settled_transaction(server):
    payload = call(server, "get_transaction_status", {"transaction_id": "TXN001"})
    assert payload["found"] is True
    assert payload["status"] == "settled"
    assert payload["net_amount"] == "1496.25"


def test_get_transaction_status_returns_a_held_transaction(server):
    payload = call(server, "get_transaction_status", {"transaction_id": "TXN005"})
    assert payload["status"] == "held"
    assert payload["hold_reasons"] == ["fraud_review_required"]


def test_get_transaction_status_handles_an_unknown_id(server):
    payload = call(server, "get_transaction_status", {"transaction_id": "TXN999"})
    assert payload["found"] is False
    assert "TXN999" in payload["message"]


def test_list_pipeline_results_returns_the_whole_run(server):
    payload = call(server, "list_pipeline_results")
    assert payload["total"] == 8
    assert payload["by_status"] == {"held": 1, "rejected": 2, "settled": 5}


def test_pipeline_summary_resource_returns_markdown(server):
    text = read_resource(server, "pipeline://summary")
    assert text.startswith("# Pipeline run summary")
    assert "TXN005" in text


def test_mcp_responses_never_leak_raw_accounts(server):
    payload = call(server, "list_pipeline_results")
    assert "ACC-" not in json.dumps(payload)
