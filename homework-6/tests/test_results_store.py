"""Unit tests for the read-only results store behind the MCP server (spec task T-7)."""

from __future__ import annotations

from agents import results_store
from agents.results_store import (
    get_transaction_status,
    latest_summary_text,
    list_pipeline_results,
    load_results,
)


def test_get_transaction_status_returns_the_settlement_view(completed_run):
    status = get_transaction_status("TXN001", completed_run.shared)

    assert status["found"] is True
    assert status["status"] == "settled"
    assert status["amount"] == "1500.00"
    assert status["currency"] == "USD"
    assert status["risk_level"] == "low"
    assert status["settlement_id"] == "STL-TXN001"
    assert status["net_amount"] == "1496.25"
    assert status["finalised_by"] == "settlement_processor"


def test_get_transaction_status_reports_a_hold(completed_run):
    status = get_transaction_status("TXN005", completed_run.shared)
    assert status["status"] == "held"
    assert status["hold_reasons"] == ["fraud_review_required"]
    assert status["ctr_required"] is True


def test_get_transaction_status_reports_a_rejection(completed_run):
    status = get_transaction_status("TXN006", completed_run.shared)
    assert status["status"] == "rejected"
    assert status["rejection_reasons"] == ["unknown_currency:XYZ"]
    assert status["settlement_id"] is None


def test_ec_15_unknown_transaction_id_is_a_readable_answer(completed_run):
    status = get_transaction_status("NOPE", completed_run.shared)
    assert status == {
        "found": False,
        "transaction_id": "NOPE",
        "message": status["message"],
    }
    assert "integrator.py" in status["message"]


def test_transaction_id_is_trimmed(completed_run):
    assert get_transaction_status("  TXN001  ", completed_run.shared)["found"] is True


def test_list_pipeline_results_summarises_every_transaction(completed_run):
    listing = list_pipeline_results(completed_run.shared)

    assert listing["total"] == 8
    assert listing["by_status"] == {"held": 1, "rejected": 2, "settled": 5}
    assert [item["transaction_id"] for item in listing["transactions"]] == [
        f"TXN00{index}" for index in range(1, 9)
    ]


def test_latest_summary_text_returns_the_markdown_report(completed_run):
    text = latest_summary_text(completed_run.shared)
    assert text.startswith("# Pipeline run summary")


def test_latest_summary_text_explains_a_missing_report(tmp_path):
    text = latest_summary_text(tmp_path / "shared")
    assert "No pipeline summary available yet" in text


def test_load_results_on_a_missing_workspace(tmp_path):
    assert load_results(tmp_path / "absent") == []


def test_default_shared_root_points_at_the_project(monkeypatch, completed_run):
    """The MCP server calls these functions without an explicit root."""
    monkeypatch.setattr(results_store, "DEFAULT_SHARED_ROOT", completed_run.shared)
    assert list_pipeline_results()["total"] == 8
    assert get_transaction_status("TXN002")["found"] is True
    assert latest_summary_text().startswith("# Pipeline run summary")
