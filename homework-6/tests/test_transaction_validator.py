"""Unit tests for the transaction validator (spec task T-1, edge cases EC-01/02/04/05/07)."""

from __future__ import annotations

import json

import pytest

from agents.protocol import TERMINAL_TARGET, Workspace
from agents.transaction_validator import (
    NEXT_AGENT,
    TransactionValidator,
    dry_run,
    main,
    redact_transaction,
    render_dry_run,
    validate_transaction,
)

# --------------------------------------------------------------------------------------
# validate_transaction — the pure decision function
# --------------------------------------------------------------------------------------


def test_valid_transaction_has_no_reasons(make_transaction):
    assert validate_transaction(make_transaction()) == []


@pytest.mark.parametrize(
    "field",
    [
        "transaction_id",
        "timestamp",
        "source_account",
        "destination_account",
        "amount",
        "currency",
        "transaction_type",
    ],
)
def test_missing_required_field_is_reported(make_transaction, field):
    transaction = make_transaction()
    del transaction[field]
    assert f"missing_field:{field}" in validate_transaction(transaction)


def test_blank_string_counts_as_missing(make_transaction):
    assert "missing_field:transaction_id" in validate_transaction(make_transaction(transaction_id="  "))


def test_ec_02_unknown_currency_is_rejected(make_transaction):
    reasons = validate_transaction(make_transaction(currency="XYZ"))
    assert "unknown_currency:XYZ" in reasons


def test_ec_01_negative_amount_is_rejected(make_transaction):
    reasons = validate_transaction(make_transaction(amount="-100.00", transaction_type="refund"))
    assert reasons == ["non_positive_amount"]


def test_zero_amount_is_rejected(make_transaction):
    assert "non_positive_amount" in validate_transaction(make_transaction(amount="0.00"))


def test_unparseable_amount_is_rejected(make_transaction):
    assert validate_transaction(make_transaction(amount="a lot")) == ["invalid_amount"]


def test_float_amount_is_rejected(make_transaction):
    assert validate_transaction(make_transaction(amount=1500.0)) == ["invalid_amount"]


def test_ec_04_too_many_decimal_places_is_rejected(make_transaction):
    assert "too_many_decimal_places" in validate_transaction(make_transaction(amount="10.005"))


def test_ec_05_jpy_amount_without_decimals_is_valid(make_transaction):
    assert validate_transaction(make_transaction(amount="1500", currency="JPY")) == []


def test_jpy_amount_with_decimals_is_rejected(make_transaction):
    assert "too_many_decimal_places" in validate_transaction(
        make_transaction(amount="1500.50", currency="JPY")
    )


def test_decimal_place_check_is_skipped_for_unknown_currency(make_transaction):
    reasons = validate_transaction(make_transaction(amount="10.00567", currency="XYZ"))
    assert reasons == ["unknown_currency:XYZ"]


def test_invalid_timestamp_is_rejected(make_transaction):
    assert "invalid_timestamp" in validate_transaction(make_transaction(timestamp="16/03/2026"))


@pytest.mark.parametrize("field", ["source_account", "destination_account"])
def test_invalid_account_format_is_rejected(make_transaction, field):
    reasons = validate_transaction(make_transaction(**{field: "1001"}))
    assert f"invalid_account_format:{field}" in reasons


def test_ec_07_same_source_and_destination_is_rejected(make_transaction):
    reasons = validate_transaction(
        make_transaction(source_account="ACC-1001", destination_account="ACC-1001")
    )
    assert "same_source_and_destination" in reasons


def test_unknown_transaction_type_is_rejected(make_transaction):
    reasons = validate_transaction(make_transaction(transaction_type="teleport"))
    assert "unknown_transaction_type:teleport" in reasons


def test_non_object_metadata_is_rejected(make_transaction):
    assert "invalid_metadata" in validate_transaction(make_transaction(metadata="online"))


def test_every_failing_check_is_reported_not_just_the_first(make_transaction):
    reasons = validate_transaction(
        make_transaction(amount="-1", currency="XYZ", transaction_type="teleport", timestamp="nope")
    )
    assert {
        "unknown_currency:XYZ",
        "non_positive_amount",
        "invalid_timestamp",
        "unknown_transaction_type:teleport",
    } <= set(reasons)


def test_instance_alias_matches_module_function(make_transaction, workspace):
    validator = TransactionValidator(workspace)
    transaction = make_transaction(currency="XYZ")
    assert validator.validate(transaction) == validate_transaction(transaction)


# --------------------------------------------------------------------------------------
# Redaction (IN-2)
# --------------------------------------------------------------------------------------


def test_redact_transaction_masks_accounts_and_drops_description(make_transaction):
    redacted = redact_transaction(make_transaction())
    assert redacted["source_account"] == "****1001"
    assert redacted["destination_account"] == "****2001"
    assert redacted["description"] == "[redacted]"


def test_redact_transaction_copies_metadata(make_transaction):
    original = make_transaction()
    redacted = redact_transaction(original)
    redacted["metadata"]["channel"] = "changed"
    assert original["metadata"]["channel"] == "online"


def test_redact_transaction_tolerates_missing_fields():
    assert redact_transaction({"transaction_id": "TXN001"}) == {"transaction_id": "TXN001"}


# --------------------------------------------------------------------------------------
# Message handling
# --------------------------------------------------------------------------------------


def test_valid_message_is_forwarded_to_the_fraud_detector(workspace, make_message):
    outgoing = TransactionValidator(workspace).process_message(make_message())
    assert outgoing["target_agent"] == NEXT_AGENT
    assert outgoing["data"]["status"] == "validated"
    assert outgoing["data"]["validation"]["valid"] is True
    assert outgoing["data"]["source_account"] == "****1001"


def test_amount_is_normalised_to_the_minor_unit(workspace, make_message):
    outgoing = TransactionValidator(workspace).process_message(make_message(amount="1500"))
    assert outgoing["data"]["amount"] == "1500.00"


def test_invalid_message_becomes_a_terminal_rejection(workspace, make_message):
    outgoing = TransactionValidator(workspace).process_message(make_message(currency="XYZ"))
    assert outgoing["target_agent"] == TERMINAL_TARGET
    assert outgoing["data"]["status"] == "rejected"
    assert outgoing["data"]["rejection_reasons"] == ["unknown_currency:XYZ"]
    assert outgoing["data"]["rejection_reason"] == "unknown_currency:XYZ"


def test_run_drains_the_input_directory(workspace, make_message):
    workspace.write_message(workspace.input_dir, make_message(transaction_id="TXN001"))
    workspace.write_message(
        workspace.input_dir, make_message(transaction_id="TXN002", currency="XYZ")
    )

    emitted = TransactionValidator(workspace).run()

    assert len(emitted) == 2
    assert list(workspace.input_dir.glob("*.json")) == []
    assert len(list(workspace.processing_dir.glob("*.json"))) == 2
    assert len(list(workspace.output_dir.glob("*.json"))) == 1
    assert len(list(workspace.results_dir.glob("*.json"))) == 1


def test_ec_10_malformed_inbox_file_is_quarantined(workspace, make_message):
    (workspace.input_dir / "broken.json").write_text("{not json", encoding="utf-8")
    workspace.write_message(workspace.input_dir, make_message(transaction_id="TXN001"))

    emitted = TransactionValidator(workspace).run()

    assert len(emitted) == 1
    assert (workspace.quarantine_dir / "broken.json").exists()
    outcomes = [entry["outcome"] for entry in workspace.audit_logger().entries()]
    assert "quarantined" in outcomes


def test_run_writes_an_audit_entry_per_message(workspace, make_message):
    workspace.write_message(workspace.input_dir, make_message(transaction_id="TXN001"))
    TransactionValidator(workspace).run()
    entries = workspace.audit_logger().entries()
    assert entries[-1]["agent"] == "transaction_validator"
    assert entries[-1]["transaction_id"] == "TXN001"
    assert entries[-1]["outcome"] == "validated"


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def test_dry_run_counts_the_sample_file():
    report = dry_run()
    assert report["total"] == 8
    assert report["valid"] == 6
    assert report["invalid"] == 2
    invalid = {row["transaction_id"]: row["reasons"] for row in report["rows"] if not row["valid"]}
    assert invalid == {"TXN006": ["unknown_currency:XYZ"], "TXN007": ["non_positive_amount"]}


def test_dry_run_handles_records_without_an_id(tmp_path):
    path = tmp_path / "sample.json"
    path.write_text(json.dumps([{"amount": "1.00"}]), encoding="utf-8")
    assert dry_run(path)["rows"][0]["transaction_id"] == "UNKNOWN"


def test_render_dry_run_contains_every_row():
    rendered = render_dry_run(dry_run())
    assert "TXN006" in rendered and "unknown_currency:XYZ" in rendered
    assert "total=8  valid=6  invalid=2" in rendered


def test_main_dry_run_writes_nothing(tmp_path, capsys):
    shared = tmp_path / "shared"
    assert main(["--dry-run", "--shared", str(shared)]) == 0
    assert not shared.exists()
    assert "DRY RUN" in capsys.readouterr().out


def test_main_without_dry_run_processes_the_workspace(tmp_path, capsys, make_message):
    shared = tmp_path / "shared"
    workspace = Workspace.create(shared)
    workspace.write_message(workspace.input_dir, make_message(transaction_id="TXN001"))

    assert main(["--shared", str(shared)]) == 0
    assert "processed 1 message(s)" in capsys.readouterr().out
