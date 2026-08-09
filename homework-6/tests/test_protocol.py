"""Unit tests for the shared protocol layer (spec task T-0)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from agents import protocol
from agents.protocol import (
    AuditLogger,
    MoneyError,
    ProtocolError,
    Workspace,
    assert_no_plaintext_pii,
    build_message,
    format_money,
    mask_account,
    minor_units,
    parse_amount,
    parse_timestamp,
    quantize_money,
    transaction_id_of,
    usd_equivalent,
    utc_now_iso,
    validate_message,
)

# --------------------------------------------------------------------------------------
# Time and identifiers
# --------------------------------------------------------------------------------------


def test_utc_now_iso_is_zulu_suffixed():
    stamp = utc_now_iso()
    assert stamp.endswith("Z")
    assert parse_timestamp(stamp).tzinfo is not None


def test_new_message_id_is_unique():
    assert protocol.new_message_id() != protocol.new_message_id()


@pytest.mark.parametrize(
    "raw,expected_hour",
    [("2026-03-16T09:00:00Z", 9), ("2026-03-16T02:47:00z", 2), ("2026-03-16T11:00:00+02:00", 9)],
)
def test_parse_timestamp_accepts_iso_variants(raw, expected_hour):
    assert parse_timestamp(raw).hour == expected_hour


def test_parse_timestamp_assumes_utc_when_naive():
    assert parse_timestamp("2026-03-16T09:00:00").hour == 9


@pytest.mark.parametrize("raw", ["", "   ", None, 42, "not-a-date"])
def test_parse_timestamp_rejects_garbage(raw):
    with pytest.raises(ProtocolError):
        parse_timestamp(raw)


# --------------------------------------------------------------------------------------
# Money (IN-1)
# --------------------------------------------------------------------------------------


def test_parse_amount_from_string_is_exact():
    assert parse_amount("1500.00") == Decimal("1500.00")


def test_parse_amount_accepts_int_and_decimal():
    assert parse_amount(1500) == Decimal("1500")
    assert parse_amount(Decimal("2.50")) == Decimal("2.50")


@pytest.mark.parametrize("raw", [1500.0, 0.1, True])
def test_parse_amount_rejects_float_and_bool(raw):
    with pytest.raises(MoneyError):
        parse_amount(raw)


@pytest.mark.parametrize("raw", ["", "   ", None, "abc", [], {}])
def test_parse_amount_rejects_unparseable(raw):
    with pytest.raises(MoneyError):
        parse_amount(raw)


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_parse_amount_rejects_non_finite(raw):
    with pytest.raises(MoneyError):
        parse_amount(raw)


def test_quantize_money_rounds_half_up_not_bankers():
    # Python's decimal default is ROUND_HALF_EVEN, which would give 0.12 here.
    assert quantize_money(Decimal("0.125"), "USD") == Decimal("0.13")
    assert quantize_money(Decimal("0.135"), "USD") == Decimal("0.14")


def test_quantize_money_respects_zero_minor_unit_currency():
    assert quantize_money(Decimal("1500.4"), "JPY") == Decimal("1500")
    assert quantize_money(Decimal("1500.5"), "JPY") == Decimal("1501")


def test_minor_units_rejects_unknown_currency():
    with pytest.raises(MoneyError):
        minor_units("XYZ")


def test_format_money_is_canonical():
    assert format_money(Decimal("1500"), "USD") == "1500.00"
    assert format_money(Decimal("1500.00"), "JPY") == "1500"


def test_usd_equivalent_uses_the_rate_table():
    assert usd_equivalent(Decimal("100"), "USD") == Decimal("100.00")
    assert usd_equivalent(Decimal("500"), "EUR") == Decimal("545.00")


def test_usd_equivalent_rejects_unknown_currency():
    with pytest.raises(MoneyError):
        usd_equivalent(Decimal("1"), "XYZ")


# --------------------------------------------------------------------------------------
# PII masking (IN-2)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [("ACC-1001", "****1001"), ("ACC-9999", "****9999"), ("12", "****12"), (None, "****")],
)
def test_mask_account(raw, expected):
    assert mask_account(raw) == expected


def test_assert_no_plaintext_pii_accepts_masked_payloads():
    assert_no_plaintext_pii({"a": ["****1001", {"b": "fine"}], "c": 3, "d": None})


@pytest.mark.parametrize(
    "payload",
    ["ACC-1001", {"account": "ACC-1001"}, {"nested": [{"x": "sent to ACC-2001 today"}]}],
)
def test_assert_no_plaintext_pii_rejects_raw_accounts(payload):
    with pytest.raises(ProtocolError):
        assert_no_plaintext_pii(payload)


# --------------------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------------------


def test_build_message_round_trips_validation():
    message = build_message("a", "b", "transaction", {"transaction_id": "TXN001"})
    validate_message(message)
    assert set(message) == set(protocol.MESSAGE_FIELDS)
    assert message["message_id"] != build_message("a", "b", "t", {})["message_id"]


def test_build_message_honours_explicit_id_and_timestamp():
    message = build_message(
        "a", "b", "t", {}, message_id="fixed-id", timestamp="2026-03-16T00:00:00Z"
    )
    assert message["message_id"] == "fixed-id"
    assert message["timestamp"] == "2026-03-16T00:00:00Z"


@pytest.mark.parametrize("field", protocol.MESSAGE_FIELDS)
def test_validate_message_reports_missing_field(field):
    message = build_message("a", "b", "t", {})
    del message[field]
    with pytest.raises(ProtocolError, match=field):
        validate_message(message)


@pytest.mark.parametrize("bad", ["", "   ", 5, None])
def test_validate_message_rejects_blank_string_fields(bad):
    message = build_message("a", "b", "t", {})
    message["source_agent"] = bad
    with pytest.raises(ProtocolError):
        validate_message(message)


def test_validate_message_rejects_non_object_data():
    message = build_message("a", "b", "t", {})
    message["data"] = ["not", "an", "object"]
    with pytest.raises(ProtocolError):
        validate_message(message)


def test_validate_message_rejects_non_dict():
    with pytest.raises(ProtocolError):
        validate_message(["not a message"])


def test_transaction_id_of_falls_back_to_unknown():
    assert transaction_id_of({"data": {"transaction_id": "TXN001"}}) == "TXN001"
    assert transaction_id_of({"data": {}}) == "UNKNOWN"
    assert transaction_id_of({}) == "UNKNOWN"


# --------------------------------------------------------------------------------------
# Audit trail (MO-4)
# --------------------------------------------------------------------------------------


def test_audit_logger_appends_iso_timestamped_records(tmp_path):
    logger = AuditLogger(tmp_path / "audit" / "audit-log.jsonl")
    logger.record("transaction_validator", "TXN001", "validated", {"next_agent": "fraud_detector"})
    logger.record("fraud_detector", "TXN001", "fraud_cleared")

    entries = logger.entries()
    assert [entry["agent"] for entry in entries] == ["transaction_validator", "fraud_detector"]
    assert all(entry["timestamp"].endswith("Z") for entry in entries)
    assert entries[0]["transaction_id"] == "TXN001"
    assert entries[1]["detail"] is None


def test_audit_logger_refuses_unmasked_account(tmp_path):
    logger = AuditLogger(tmp_path / "audit-log.jsonl")
    with pytest.raises(ProtocolError):
        logger.record("agent", "TXN001", "ok", {"source_account": "ACC-1001"})
    assert logger.entries() == []


def test_audit_logger_entries_on_missing_file(tmp_path):
    assert AuditLogger(tmp_path / "nothing.jsonl").entries() == []


# --------------------------------------------------------------------------------------
# Workspace
# --------------------------------------------------------------------------------------


def test_workspace_create_makes_every_subdirectory(tmp_path):
    workspace = Workspace.create(tmp_path / "shared")
    for name in protocol.SHARED_SUBDIRS:
        assert (workspace.root / name).is_dir()


def test_workspace_create_reset_clears_previous_content(tmp_path):
    workspace = Workspace.create(tmp_path / "shared")
    (workspace.results_dir / "stale.json").write_text("{}", encoding="utf-8")
    workspace = Workspace.create(tmp_path / "shared", reset=True)
    assert list(workspace.results_dir.glob("*")) == []


def test_workspace_dir_rejects_unknown_name(workspace):
    with pytest.raises(ProtocolError):
        workspace.dir("nope")


def test_workspace_named_directories_resolve(workspace):
    assert workspace.input_dir.name == "input"
    assert workspace.processing_dir.name == "processing"
    assert workspace.output_dir.name == "output"
    assert workspace.results_dir.name == "results"
    assert workspace.reports_dir.name == "reports"
    assert workspace.quarantine_dir.name == "quarantine"
    assert workspace.audit_log_path.name == "audit-log.jsonl"
    assert isinstance(workspace.audit_logger(), AuditLogger)


def test_write_message_names_file_after_transaction_and_message_id(workspace):
    message = build_message("a", "b", "transaction", {"transaction_id": "TXN001"})
    path = workspace.write_message(workspace.input_dir, message)
    assert path.name.startswith("TXN001-")
    assert json.loads(path.read_text(encoding="utf-8")) == message


def test_write_message_allows_raw_accounts_in_flight(workspace):
    message = build_message("a", "b", "transaction", {"source_account": "ACC-1001"})
    assert workspace.write_message(workspace.input_dir, message).exists()


def test_write_message_enforces_masking_for_terminal_results(workspace):
    message = build_message("a", "b", "transaction", {"source_account": "ACC-1001"})
    with pytest.raises(ProtocolError):
        workspace.write_message(workspace.results_dir, message, require_masked=True)


def test_iter_inbox_filters_by_target_agent(workspace):
    workspace.write_message(
        workspace.output_dir, build_message("a", "fraud_detector", "t", {"transaction_id": "T1"})
    )
    workspace.write_message(
        workspace.output_dir, build_message("a", "settlement_processor", "t", {"transaction_id": "T2"})
    )
    found = list(workspace.iter_inbox(workspace.output_dir, "fraud_detector"))
    assert len(found) == 1
    assert found[0][1]["data"]["transaction_id"] == "T1"


def test_iter_inbox_reports_malformed_files(workspace):
    (workspace.input_dir / "broken.json").write_text("{not json", encoding="utf-8")
    (workspace.input_dir / "incomplete.json").write_text('{"message_id": "x"}', encoding="utf-8")
    problems = [item for item in workspace.iter_inbox(workspace.input_dir, "anyone") if item[2]]
    assert len(problems) == 2
    assert all(message is None for _, message, _ in problems)


def test_iter_inbox_on_missing_directory_yields_nothing(tmp_path):
    workspace = Workspace(root=tmp_path / "absent")
    assert list(workspace.iter_inbox(tmp_path / "absent" / "input", "x")) == []


def test_claim_moves_the_file_into_processing(workspace):
    message = build_message("a", "transaction_validator", "t", {"transaction_id": "TXN001"})
    path = workspace.write_message(workspace.input_dir, message)
    claimed = workspace.claim(path)
    assert claimed.parent == workspace.processing_dir
    assert not path.exists()


def test_quarantine_moves_the_file_and_records_the_reason(workspace):
    path = workspace.input_dir / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    moved = workspace.quarantine(path, "invalid JSON")
    assert moved.parent == workspace.quarantine_dir
    assert Path(str(moved) + ".reason").read_text(encoding="utf-8") == "invalid JSON"


def test_results_are_sorted_by_transaction_id(workspace):
    for transaction_id in ("TXN003", "TXN001", "TXN002"):
        workspace.write_message(
            workspace.results_dir,
            build_message("a", protocol.TERMINAL_TARGET, "t", {"transaction_id": transaction_id}),
        )
    ids = [record["data"]["transaction_id"] for record in workspace.results()]
    assert ids == ["TXN001", "TXN002", "TXN003"]
