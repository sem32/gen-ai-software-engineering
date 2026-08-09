"""End-to-end integration tests (spec task T-6 and the §8 outcome table)."""

from __future__ import annotations

import json

import pytest

from agents.protocol import Workspace
from conftest import SAMPLE_PATH
from integrator import load_sample, main, render_results_table, run_pipeline, seed_input

#: The specification's own regression expectation (spec §8).
EXPECTED = {
    "TXN001": {"status": "settled", "risk_score": 0, "risk_level": "low"},
    "TXN002": {"status": "settled", "risk_score": 40, "risk_level": "medium"},
    "TXN003": {"status": "settled", "risk_score": 35, "risk_level": "medium"},
    "TXN004": {"status": "settled", "risk_score": 40, "risk_level": "medium"},
    "TXN005": {"status": "held", "risk_score": 60, "risk_level": "high"},
    "TXN006": {"status": "rejected", "risk_score": None, "risk_level": None},
    "TXN007": {"status": "rejected", "risk_score": None, "risk_level": None},
    "TXN008": {"status": "settled", "risk_score": 0, "risk_level": "low"},
}


def by_id(summary):
    return {row["transaction_id"]: row for row in summary["transactions"]}


# --------------------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------------------


def test_every_transaction_reaches_a_terminal_state(completed_run):
    summary = completed_run.summary
    assert summary["total_transactions"] == 8
    assert summary["reconciled"] is True
    assert summary["pending_messages"] == 0
    assert len(list(completed_run.workspace.results_dir.glob("*.json"))) == 8


@pytest.mark.parametrize("transaction_id", sorted(EXPECTED))
def test_specification_outcome_table(completed_run, transaction_id):
    row = by_id(completed_run.summary)[transaction_id]
    expected = EXPECTED[transaction_id]
    assert row["status"] == expected["status"]
    assert row["risk_score"] == expected["risk_score"]
    assert row["risk_level"] == expected["risk_level"]


def test_intermediate_directories_are_empty_after_the_run(completed_run):
    workspace = completed_run.workspace
    assert list(workspace.input_dir.glob("*.json")) == []
    assert list(workspace.output_dir.glob("*.json")) == []
    assert list(workspace.quarantine_dir.glob("*")) == []


def test_every_message_passed_through_processing(completed_run):
    # 8 validated + 6 scored + 6 screened + 5 settled = 25 claims
    assert len(list(completed_run.workspace.processing_dir.glob("*.json"))) == 25


def test_audit_trail_covers_every_agent(completed_run):
    entries = completed_run.workspace.audit_logger().entries()
    agents_seen = {entry["agent"] for entry in entries}
    assert agents_seen == {
        "integrator",
        "transaction_validator",
        "fraud_detector",
        "compliance_checker",
        "settlement_processor",
        "reporting_agent",
    }
    assert all(entry["timestamp"].endswith("Z") for entry in entries)


def test_audit_trail_never_contains_a_raw_account(completed_run):
    raw = completed_run.workspace.audit_log_path.read_text(encoding="utf-8")
    assert "ACC-" not in raw


def test_results_never_contain_a_raw_account_or_description(completed_run):
    for path in completed_run.workspace.results_dir.glob("*.json"):
        content = path.read_text(encoding="utf-8")
        assert "ACC-" not in content
        assert "Monthly rent payment" not in content
        assert "[redacted]" in content


def test_pipeline_is_reproducible(tmp_path):
    first = run_pipeline(SAMPLE_PATH, tmp_path / "a", verbose=False)
    second = run_pipeline(SAMPLE_PATH, tmp_path / "b", verbose=False)
    assert by_id(first).keys() == by_id(second).keys()
    for transaction_id, row in by_id(first).items():
        other = by_id(second)[transaction_id]
        assert (row["status"], row["risk_score"]) == (other["status"], other["risk_score"])


def test_rerunning_into_the_same_workspace_resets_it(tmp_path):
    shared = tmp_path / "shared"
    run_pipeline(SAMPLE_PATH, shared, verbose=False)
    summary = run_pipeline(SAMPLE_PATH, shared, verbose=False)
    assert summary["total_transactions"] == 8


# --------------------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------------------


def test_ec_09_empty_input_file(tmp_path):
    sample = tmp_path / "empty.json"
    sample.write_text("[]", encoding="utf-8")
    summary = run_pipeline(sample, tmp_path / "shared", verbose=False)
    assert summary["total_transactions"] == 0
    assert summary["reconciled"] is True


def test_ec_10_malformed_inbox_file_is_quarantined_and_the_run_continues(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    workspace = Workspace.create(shared)
    (workspace.input_dir / "junk.json").write_text("{oops", encoding="utf-8")

    summary = run_pipeline(SAMPLE_PATH, shared, reset=False, verbose=False)

    assert summary["total_transactions"] == 8
    assert summary["quarantined_messages"] == 1
    assert (workspace.quarantine_dir / "junk.json").exists()


def test_ec_12_duplicate_transaction_ids_do_not_overwrite_each_other(tmp_path):
    sample = tmp_path / "duplicates.json"
    records = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))[:1]
    sample.write_text(json.dumps(records * 2), encoding="utf-8")

    summary = run_pipeline(sample, tmp_path / "shared", verbose=False)

    assert summary["total_transactions"] == 2
    assert [row["transaction_id"] for row in summary["transactions"]] == ["TXN001", "TXN001"]


def test_load_sample_rejects_a_non_array_file(tmp_path):
    sample = tmp_path / "object.json"
    sample.write_text('{"transaction_id": "TXN001"}', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON array"):
        load_sample(sample)


def test_seed_input_writes_one_message_per_transaction(workspace):
    paths = seed_input(workspace, [{"transaction_id": "TXN001"}, {"transaction_id": "TXN002"}])
    assert len(paths) == 2
    assert all(path.parent == workspace.input_dir for path in paths)
    outcomes = [entry["outcome"] for entry in workspace.audit_logger().entries()]
    assert outcomes == ["ingested", "ingested"]


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def test_render_results_table_lists_every_transaction(completed_run):
    table = render_results_table(completed_run.summary)
    for transaction_id in EXPECTED:
        assert transaction_id in table
    assert "reconciled=yes" in table
    assert "total=8" in table


def test_render_results_table_flags_a_failed_reconciliation(completed_run):
    summary = dict(completed_run.summary, reconciled=False)
    assert "reconciled=NO" in render_results_table(summary)


def test_main_exits_zero_and_prints_the_table(tmp_path, capsys):
    exit_code = main(["--sample", str(SAMPLE_PATH), "--shared", str(tmp_path / "shared")])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "PIPELINE RESULTS" in out
    assert "[transaction_validator] processed 8 message(s)" in out


def test_main_quiet_mode_suppresses_progress(tmp_path, capsys):
    assert main(["--sample", str(SAMPLE_PATH), "--shared", str(tmp_path / "shared"), "--quiet"]) == 0
    assert capsys.readouterr().out == ""


def test_main_no_reset_keeps_previous_results(tmp_path, capsys):
    shared = tmp_path / "shared"
    assert main(["--sample", str(SAMPLE_PATH), "--shared", str(shared), "--quiet"]) == 0
    assert main(["--sample", str(SAMPLE_PATH), "--shared", str(shared), "--no-reset", "--quiet"]) == 1
    assert "RECONCILIATION FAILED" in capsys.readouterr().err
