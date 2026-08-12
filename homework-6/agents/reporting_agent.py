"""Agent 5 of the runtime pipeline — reporting (spec task T-5).

Reads every terminal result from ``shared/results`` and produces the run summary as both JSON and
Markdown under ``shared/reports``. Totals are kept per currency — different currencies are never
summed into one number.
"""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - only when run as a script (PEP 366)
    import sys as _sys

    _sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "agents"

from .protocol import (
    AuditLogger,
    Workspace,
    assert_no_plaintext_pii,
    format_money,
    parse_amount,
    utc_now_iso,
)

SUMMARY_JSON = "pipeline-summary.json"
SUMMARY_MARKDOWN = "pipeline-summary.md"


class ReportingAgent:
    """Aggregates terminal results into a run summary.

    Unlike the other agents this one consumes no inbox — it reads the results directory, which is
    the pipeline's own output, and therefore runs last.
    """

    name = "reporting_agent"

    def __init__(self, workspace: Workspace, audit: AuditLogger | None = None) -> None:
        self.workspace = workspace
        self.audit = audit if audit is not None else workspace.audit_logger()

    # -- aggregation -------------------------------------------------------------------

    def build_summary(self) -> dict[str, Any]:
        results = self.workspace.results()
        by_status: Counter[str] = Counter()
        by_risk_level: Counter[str] = Counter()
        by_priority: Counter[str] = Counter()
        packs: Counter[str] = Counter()
        volume: dict[str, dict[str, Decimal]] = {}
        rejected: list[dict[str, Any]] = []
        held: list[dict[str, Any]] = []
        settled: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []

        for record in results:
            data = record.get("data") or {}
            status = str(data.get("status", "unknown"))
            currency = str(data.get("currency", "---"))
            fraud = data.get("fraud") or {}
            policy = data.get("policy") or {}
            by_status[status] += 1
            if fraud.get("risk_level"):
                by_risk_level[str(fraud["risk_level"])] += 1
            if policy.get("priority"):
                by_priority[str(policy["priority"])] += 1
            if policy.get("pack", {}).get("name"):
                packs[str(policy["pack"]["name"])] += 1

            row = {
                "transaction_id": str(data.get("transaction_id", "UNKNOWN")),
                "status": status,
                "currency": currency,
                "amount": str(data.get("amount", "-")),
                "risk_score": fraud.get("risk_score"),
                "risk_level": fraud.get("risk_level"),
                "priority": policy.get("priority"),
                "policy_tags": list(policy.get("tags") or []),
                "dual_approval_required": policy.get("dual_approval_required"),
                "detail": _detail_for(data, status),
            }
            rows.append(row)

            if status == "rejected":
                rejected.append(
                    {
                        "transaction_id": row["transaction_id"],
                        "reasons": list(data.get("rejection_reasons") or []),
                    }
                )
            elif status == "held":
                held.append(
                    {
                        "transaction_id": row["transaction_id"],
                        "hold_reasons": list((data.get("compliance") or {}).get("hold_reasons", [])),
                        "risk_score": fraud.get("risk_score"),
                    }
                )
                _accumulate(volume, currency, "held", parse_amount(data["amount"]))
            elif status == "settled":
                settlement = data.get("settlement") or {}
                settled.append(
                    {
                        "transaction_id": row["transaction_id"],
                        "currency": currency,
                        "gross_amount": settlement.get("gross_amount"),
                        "fee": settlement.get("fee"),
                        "net_amount": settlement.get("net_amount"),
                        "value_date": settlement.get("value_date"),
                        "risk_level": fraud.get("risk_level"),
                    }
                )
                _accumulate(volume, currency, "settled_gross", parse_amount(settlement["gross_amount"]))
                _accumulate(volume, currency, "settled_fees", parse_amount(settlement["fee"]))
                _accumulate(volume, currency, "settled_net", parse_amount(settlement["net_amount"]))

        summary = {
            "generated_at": utc_now_iso(),
            "total_transactions": len(results),
            "by_status": dict(sorted(by_status.items())),
            "by_risk_level": dict(sorted(by_risk_level.items())),
            "by_priority": dict(sorted(by_priority.items())),
            "rule_packs": dict(sorted(packs.items())),
            "volume_by_currency": {
                currency: {key: format_money(value, currency) for key, value in sorted(buckets.items())}
                for currency, buckets in sorted(volume.items())
            },
            "rejected": rejected,
            "held": held,
            "settled": settled,
            "transactions": rows,
        }
        assert_no_plaintext_pii(summary, where="summary")
        return summary

    # -- rendering and persistence -----------------------------------------------------

    def run(self) -> dict[str, Any]:
        summary = self.build_summary()
        reports = self.workspace.reports_dir
        reports.mkdir(parents=True, exist_ok=True)
        (reports / SUMMARY_JSON).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (reports / SUMMARY_MARKDOWN).write_text(render_markdown(summary), encoding="utf-8")
        self.audit.record(
            self.name,
            "ALL",
            "summary_written",
            {"total": summary["total_transactions"], "by_status": summary["by_status"]},
        )
        return summary


def _accumulate(
    volume: dict[str, dict[str, Decimal]], currency: str, bucket: str, amount: Decimal
) -> None:
    buckets = volume.setdefault(currency, {})
    buckets[bucket] = buckets.get(bucket, Decimal("0")) + amount


def _detail_for(data: dict[str, Any], status: str) -> str:
    if status == "rejected":
        return str(data.get("rejection_reason", ""))
    if status == "held":
        return str(data.get("hold_reason", ""))
    if status == "settled":
        settlement = data.get("settlement") or {}
        return f"net {settlement.get('net_amount')} value date {settlement.get('value_date')}"
    return ""


def render_markdown(summary: dict[str, Any]) -> str:
    """Human-readable run summary."""
    lines = [
        "# Pipeline run summary",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Transactions processed: **{summary['total_transactions']}**",
        "",
        "## Outcomes",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    for status, count in summary["by_status"].items():
        lines.append(f"| {status} | {count} |")

    lines += ["", "## Risk levels", "", "| Level | Count |", "|---|---|"]
    for level, count in summary["by_risk_level"].items():
        lines.append(f"| {level} | {count} |")

    if summary.get("by_priority"):
        lines += ["", "## Policy routing", "", "| Priority | Count |", "|---|---|"]
        for priority, count in summary["by_priority"].items():
            lines.append(f"| {priority} | {count} |")
        packs = ", ".join(f"{name} ({count})" for name, count in summary["rule_packs"].items())
        lines += ["", f"Rule pack(s) applied: {packs}."]

    lines += ["", "## Volume by currency", "", "| Currency | Bucket | Amount |", "|---|---|---|"]
    for currency, buckets in summary["volume_by_currency"].items():
        for bucket, amount in buckets.items():
            lines.append(f"| {currency} | {bucket} | {amount} |")

    lines += [
        "",
        "## Transactions",
        "",
        "| Transaction | Status | Amount | Risk | Detail |",
        "|---|---|---|---|---|",
    ]
    for row in summary["transactions"]:
        risk = "-" if row["risk_score"] is None else f"{row['risk_score']} ({row['risk_level']})"
        lines.append(
            f"| {row['transaction_id']} | {row['status']} | {row['amount']} {row['currency']} "
            f"| {risk} | {row['detail']} |"
        )

    if summary["rejected"]:
        lines += ["", "## Rejected transactions", ""]
        for item in summary["rejected"]:
            lines.append(f"- **{item['transaction_id']}** — {', '.join(item['reasons'])}")

    if summary["held"]:
        lines += ["", "## Held transactions", ""]
        for item in summary["held"]:
            lines.append(f"- **{item['transaction_id']}** — {', '.join(item['hold_reasons'])}")

    return "\n".join(lines) + "\n"
