"""Unit tests for the compliance checker (spec task T-3, edge case EC-08)."""

from __future__ import annotations

import pytest

from agents.compliance_checker import (
    NEXT_AGENT,
    SANCTIONED_COUNTRIES,
    ComplianceChecker,
    screen_transaction,
)
from agents.fraud_detector import score_transaction
from agents.protocol import TERMINAL_TARGET


@pytest.fixture
def scored(make_transaction):
    """A transaction carrying a real fraud assessment, as compliance would receive it."""

    def _scored(**overrides):
        transaction = make_transaction(**overrides)
        transaction["fraud"] = score_transaction(transaction)
        return transaction

    return _scored


def check_named(outcome, code):
    return next(check for check in outcome["checks"] if check["code"] == code)


# --------------------------------------------------------------------------------------
# Decisions
# --------------------------------------------------------------------------------------


def test_ordinary_domestic_transaction_is_cleared(scored):
    outcome = screen_transaction(scored())
    assert outcome["decision"] == "cleared"
    assert outcome["hold_reasons"] == []
    assert outcome["ctr_required"] is False
    assert all(check["passed"] for check in outcome["checks"])


def test_large_transaction_is_cleared_but_requires_a_ctr(scored):
    outcome = screen_transaction(scored(amount="25000.00"))
    assert outcome["decision"] == "cleared"
    assert outcome["ctr_required"] is True
    assert "CTR required" in check_named(outcome, "ctr_threshold")["note"]


def test_high_risk_transaction_is_held_for_manual_review(scored):
    outcome = screen_transaction(scored(amount="75000.00"))
    assert outcome["decision"] == "held"
    assert outcome["hold_reasons"] == ["fraud_review_required"]
    assert outcome["ctr_required"] is True


def test_medium_risk_above_the_threshold_is_not_held(scored):
    outcome = screen_transaction(scored(amount="25000.00"))
    assert outcome["hold_reasons"] == []


@pytest.mark.parametrize("country", sorted(SANCTIONED_COUNTRIES))
def test_sanctioned_country_is_held(scored, country):
    outcome = screen_transaction(scored(metadata={"channel": "online", "country": country}))
    assert outcome["decision"] == "held"
    assert f"sanctioned_country:{country}" in outcome["hold_reasons"]


def test_watchlist_destination_is_held(scored):
    outcome = screen_transaction(scored(destination_account="ACC-4242"))
    assert "watchlist_destination" in outcome["hold_reasons"]


def test_watchlist_matches_masked_destinations(scored):
    outcome = screen_transaction(scored(destination_account="****4242"))
    assert "watchlist_destination" in outcome["hold_reasons"]


# --------------------------------------------------------------------------------------
# Fail closed (IN-3)
# --------------------------------------------------------------------------------------


def test_missing_country_fails_closed(scored):
    outcome = screen_transaction(scored(metadata={"channel": "online"}))
    assert outcome["decision"] == "held"
    assert "missing_country" in outcome["hold_reasons"]
    assert check_named(outcome, "sanctions")["passed"] is False


def test_ec_08_missing_fraud_assessment_fails_closed(make_transaction):
    outcome = screen_transaction(make_transaction())
    assert outcome["decision"] == "held"
    assert "missing_fraud_assessment" in outcome["hold_reasons"]


def test_non_dict_fraud_section_fails_closed(make_transaction):
    transaction = make_transaction()
    transaction["fraud"] = "cleared, trust me"
    assert "missing_fraud_assessment" in screen_transaction(transaction)["hold_reasons"]


def test_unparseable_amount_fails_closed(scored):
    transaction = scored()
    transaction["amount"] = "not a number"
    outcome = screen_transaction(transaction)
    assert outcome["decision"] == "held"
    assert "unparseable_amount" in outcome["hold_reasons"]
    assert outcome["ctr_required"] is False


# --------------------------------------------------------------------------------------
# Message handling
# --------------------------------------------------------------------------------------


def test_cleared_message_is_forwarded_to_settlement(workspace, make_message, make_transaction):
    message = make_message(target_agent="compliance_checker")
    message["data"]["fraud"] = score_transaction(make_transaction())

    outgoing = ComplianceChecker(workspace).process_message(message)

    assert outgoing["target_agent"] == NEXT_AGENT
    assert outgoing["data"]["status"] == "compliance_cleared"


def test_held_message_is_terminal(workspace, make_message, make_transaction):
    message = make_message(target_agent="compliance_checker", amount="75000.00")
    message["data"]["fraud"] = score_transaction(make_transaction(amount="75000.00"))

    outgoing = ComplianceChecker(workspace).process_message(message)

    assert outgoing["target_agent"] == TERMINAL_TARGET
    assert outgoing["data"]["status"] == "held"
    assert outgoing["data"]["hold_reason"] == "fraud_review_required"


def test_instance_alias_matches_module_function(workspace, scored):
    transaction = scored(amount="75000.00")
    assert ComplianceChecker(workspace).screen(transaction) == screen_transaction(transaction)
