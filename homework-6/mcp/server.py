"""Custom FastMCP server exposing the pipeline results (spec task T-7).

Tools
    get_transaction_status(transaction_id) -> current terminal status of one transaction
    list_pipeline_results()                -> summary of every processed transaction

Resource
    pipeline://summary                     -> the latest run summary as Markdown

Run it directly with ``python mcp/server.py`` (stdio transport), or let an MCP client start it
through ``mcp.json``.

Note on imports: this directory intentionally has **no** ``__init__.py`` and the project root is
*appended* to ``sys.path``, never prepended — otherwise ``homework-6/mcp/`` would shadow the
installed ``mcp`` package that FastMCP itself imports.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from fastmcp import FastMCP  # noqa: E402

from agents import results_store  # noqa: E402

mcp = FastMCP(name="pipeline-status")


@mcp.tool
def get_transaction_status(transaction_id: str) -> dict[str, Any]:
    """Return the current pipeline status of one transaction from shared/results.

    Args:
        transaction_id: the business identifier, e.g. ``TXN005``.

    An unknown id returns ``{"found": false, ...}`` with an explanation rather than an error.
    """
    return results_store.get_transaction_status(transaction_id)


@mcp.tool
def list_pipeline_results() -> dict[str, Any]:
    """Return a summary of every transaction processed by the last pipeline run.

    The response carries the total count, the per-status breakdown and one entry per transaction
    with its risk score, compliance outcome and settlement figures.
    """
    return results_store.list_pipeline_results()


@mcp.resource("pipeline://summary")
def pipeline_summary() -> str:
    """The latest pipeline run summary, as Markdown."""
    return results_store.latest_summary_text()


if __name__ == "__main__":
    mcp.run()
