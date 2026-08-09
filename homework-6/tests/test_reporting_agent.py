"""Unit tests for the reporting agent (spec task T-5, edge case EC-09)."""

from __future__ import annotations

import json

from agents.protocol import TERMINAL_TARGET, Workspace, build_message
from agents.reporting_agent import (
    SUMMARY_JSON,
    SUMMARY_MARKDOWN,
    ReportingAgent,
    render_markdown,
)


def test_summary_aggregates_the_whole_run(completed_run):
    summary = ReportingAgent(completed_run.workspace).build_summary()

    assert summary["total_transactions"] == 8
    assert summary["by_status"] == {"held": 1, "rejected": 2, "settled": 5}
    assert summary["by_risk_level"] == {"high": 1, "low": 2, "medium": 3}
    assert [item["transaction_id"] for item in summary["rejected"]] == ["TXN006", "TXN007"]
    assert [item["transaction_id"] for item in summary["held"]] == ["TXN005"]
    assert len(summary["settled"]) == 5


def test_volumes_are_kept_per_currency(completed_run):
    volume = ReportingAgent(completed_run.workspace).build_summary()["volume_by_currency"]

    assert set(volume) == {"USD", "EUR"}
    assert volume["USD"]["settled_gross"] == "39699.99"
    assert volume["USD"]["settled_fees"] == "61.75"
    assert volume["USD"]["settled_net"] == "39638.24"
    assert volume["USD"]["held"] == "75000.00"
    assert volume["EUR"] == {
        "settled_fees": "1.25",
        "settled_gross": "500.00",
        "settled_net": "498.75",
    }


def test_summary_contains_no_unmasked_accounts(completed_run):
    raw = json.dumps(ReportingAgent(completed_run.workspace).build_summary())
    assert "ACC-" not in raw

    # ...and the results the summary was built from carry the masked form only.
    results = json.dumps(completed_run.workspace.results())
    assert "ACC-" not in results
    assert "****1001" in results


def test_run_writes_both_report_formats(completed_run):
    workspace = completed_run.workspace
    summary = ReportingAgent(workspace).run()

    assert (workspace.reports_dir / SUMMARY_JSON).exists()
    markdown = (workspace.reports_dir / SUMMARY_MARKDOWN).read_text(encoding="utf-8")
    assert markdown.startswith("# Pipeline run summary")
    assert "TXN005" in markdown
    assert json.loads((workspace.reports_dir / SUMMARY_JSON).read_text(encoding="utf-8"))[
        "total_transactions"
    ] == summary["total_transactions"]


def test_run_records_an_audit_entry(completed_run):
    ReportingAgent(completed_run.workspace).run()
    entries = completed_run.workspace.audit_logger().entries()
    assert entries[-1] == {
        **entries[-1],
        "agent": "reporting_agent",
        "transaction_id": "ALL",
        "outcome": "summary_written",
    }


def test_ec_09_empty_results_produce_an_empty_summary(workspace):
    summary = ReportingAgent(workspace).run()

    assert summary["total_transactions"] == 0
    assert summary["by_status"] == {}
    assert summary["volume_by_currency"] == {}
    assert (workspace.reports_dir / SUMMARY_MARKDOWN).exists()


def test_unknown_status_is_counted_but_produces_no_detail(workspace):
    workspace.write_message(
        workspace.results_dir,
        build_message(
            "x", TERMINAL_TARGET, "transaction", {"transaction_id": "TXN000", "status": "unknown"}
        ),
    )
    summary = ReportingAgent(workspace).build_summary()
    assert summary["by_status"] == {"unknown": 1}
    assert summary["transactions"][0]["detail"] == ""


def test_render_markdown_includes_every_section(completed_run):
    markdown = render_markdown(ReportingAgent(completed_run.workspace).build_summary())

    for heading in (
        "## Outcomes",
        "## Risk levels",
        "## Volume by currency",
        "## Transactions",
        "## Rejected transactions",
        "## Held transactions",
    ):
        assert heading in markdown
    assert "unknown_currency:XYZ" in markdown
    assert "fraud_review_required" in markdown


def test_reporting_agent_accepts_an_injected_audit_logger(tmp_path):
    workspace = Workspace.create(tmp_path / "shared")
    logger = workspace.audit_logger()
    agent = ReportingAgent(workspace, logger)
    assert agent.audit is logger
