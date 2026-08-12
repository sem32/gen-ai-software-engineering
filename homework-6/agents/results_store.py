"""Read-only view over the pipeline's artefacts (spec task T-7).

This module is the whole business logic behind the custom MCP server. It is deliberately free of
any MCP dependency so it can be unit-tested without importing ``fastmcp``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .protocol import Workspace
from .reporting_agent import SUMMARY_MARKDOWN

DEFAULT_SHARED_ROOT = Path(__file__).resolve().parent.parent / "shared"


def _workspace(shared_root: Path | str | None = None) -> Workspace:
    """A read-only workspace handle — never creates directories."""
    return Workspace(root=Path(shared_root) if shared_root is not None else DEFAULT_SHARED_ROOT)


def load_results(shared_root: Path | str | None = None) -> list[dict[str, Any]]:
    """Every terminal result message currently on disk."""
    workspace = _workspace(shared_root)
    if not workspace.results_dir.exists():
        return []
    return workspace.results()


def _summarise(record: dict[str, Any]) -> dict[str, Any]:
    data = record.get("data") or {}
    fraud = data.get("fraud") or {}
    settlement = data.get("settlement") or {}
    compliance = data.get("compliance") or {}
    policy = data.get("policy") or {}
    return {
        "transaction_id": str(data.get("transaction_id", "UNKNOWN")),
        "status": str(data.get("status", "unknown")),
        "amount": str(data.get("amount", "-")),
        "currency": str(data.get("currency", "---")),
        "transaction_type": data.get("transaction_type"),
        "risk_score": fraud.get("risk_score"),
        "risk_level": fraud.get("risk_level"),
        "review_required": fraud.get("review_required"),
        "ctr_required": compliance.get("ctr_required"),
        "hold_reasons": (compliance.get("hold_reasons") or []) + (policy.get("hold_reasons") or []),
        "rejection_reasons": data.get("rejection_reasons") or [],
        "rule_pack": (policy.get("pack") or {}).get("name"),
        "priority": policy.get("priority"),
        "sla_hours": policy.get("sla_hours"),
        "policy_tags": policy.get("tags") or [],
        "dual_approval_required": policy.get("dual_approval_required"),
        "matched_policy_rules": [rule.get("id") for rule in policy.get("matched_rules") or []],
        "settlement_id": settlement.get("settlement_id"),
        "fee": settlement.get("fee"),
        "net_amount": settlement.get("net_amount"),
        "value_date": settlement.get("value_date"),
        "finalised_by": record.get("source_agent"),
        "finalised_at": record.get("timestamp"),
    }


def summarise_result(record: dict[str, Any]) -> dict[str, Any]:
    """Public view of one terminal result message — the shape the MCP server and API both return."""
    return _summarise(record)


def get_transaction_status(
    transaction_id: str, shared_root: Path | str | None = None
) -> dict[str, Any]:
    """Current terminal status of one transaction.

    An unknown id is a readable answer, not an exception — the caller is an LLM (edge case EC-15).
    """
    wanted = str(transaction_id).strip()
    for record in load_results(shared_root):
        data = record.get("data") or {}
        if str(data.get("transaction_id", "")) == wanted:
            return {"found": True, **_summarise(record)}
    return {
        "found": False,
        "transaction_id": wanted,
        "message": (
            f"No result for {wanted!r} in shared/results. "
            "Run the pipeline first (`python integrator.py`)."
        ),
    }


def list_pipeline_results(shared_root: Path | str | None = None) -> dict[str, Any]:
    """Summary of every processed transaction."""
    records = load_results(shared_root)
    transactions = [_summarise(record) for record in records]
    by_status = Counter(item["status"] for item in transactions)
    return {
        "total": len(transactions),
        "by_status": dict(sorted(by_status.items())),
        "transactions": transactions,
    }


def latest_summary_text(shared_root: Path | str | None = None) -> str:
    """The latest run summary as Markdown, or a readable explanation of why it is missing."""
    path = _workspace(shared_root).reports_dir / SUMMARY_MARKDOWN
    if not path.exists():
        return (
            "No pipeline summary available yet. Run `python integrator.py` to produce "
            "shared/reports/pipeline-summary.md."
        )
    return path.read_text(encoding="utf-8")
