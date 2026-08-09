"""Unit tests for the fraud detector (spec task T-2, edge cases EC-03/EC-06)."""

from __future__ import annotations

import pytest

from agents.fraud_detector import (
    HIGH_THRESHOLD,
    MAX_SCORE,
    MEDIUM_THRESHOLD,
    NEXT_AGENT,
    RULES,
    FraudDetector,
    build_context,
    score_transaction,
)


def codes(assessment) -> set[str]:
    return {rule["code"] for rule in assessment["triggered_rules"]}


# --------------------------------------------------------------------------------------
# Individual rules
# --------------------------------------------------------------------------------------


def test_low_risk_domestic_business_hours_transaction_scores_zero(make_transaction):
    assessment = score_transaction(make_transaction())
    assert assessment["risk_score"] == 0
    assert assessment["risk_level"] == "low"
    assert assessment["review_required"] is False
    assert assessment["triggered_rules"] == []


def test_high_value_rule_fires_exactly_at_the_threshold(make_transaction):
    assert "high_value" in codes(score_transaction(make_transaction(amount="10000.00")))
    assert "high_value" not in codes(score_transaction(make_transaction(amount="9999.99")))


def test_very_high_value_stacks_on_top_of_high_value(make_transaction):
    assessment = score_transaction(make_transaction(amount="75000.00"))
    assert codes(assessment) == {"high_value", "very_high_value"}
    assert assessment["risk_score"] == 60
    assert assessment["risk_level"] == "high"
    assert assessment["review_required"] is True


def test_ec_03_structuring_window(make_transaction):
    assert "structuring" in codes(score_transaction(make_transaction(amount="9999.99")))
    assert "structuring" in codes(score_transaction(make_transaction(amount="9000.00")))
    assert "structuring" not in codes(score_transaction(make_transaction(amount="8999.99")))


def test_ec_06_unusual_timing_and_off_hours_api(make_transaction):
    transaction = make_transaction(
        timestamp="2026-03-16T02:47:00Z", metadata={"channel": "api", "country": "US"}
    )
    assessment = score_transaction(transaction)
    assert codes(assessment) == {"unusual_timing", "off_hours_api"}
    assert assessment["risk_score"] == 40


def test_unusual_timing_boundary_is_half_open(make_transaction):
    assert "unusual_timing" in codes(
        score_transaction(make_transaction(timestamp="2026-03-16T05:59:59Z"))
    )
    assert "unusual_timing" not in codes(
        score_transaction(make_transaction(timestamp="2026-03-16T06:00:00Z"))
    )


def test_off_hours_api_needs_both_conditions(make_transaction):
    daytime_api = make_transaction(metadata={"channel": "api", "country": "US"})
    assert "off_hours_api" not in codes(score_transaction(daytime_api))

    night_branch = make_transaction(
        timestamp="2026-03-16T02:00:00Z", metadata={"channel": "branch", "country": "US"}
    )
    assert "off_hours_api" not in codes(score_transaction(night_branch))


def test_cross_border_rule_compares_country_against_the_currency_region(make_transaction):
    assert "cross_border" in codes(
        score_transaction(make_transaction(metadata={"channel": "online", "country": "GB"}))
    )
    assert "cross_border" not in codes(
        score_transaction(
            make_transaction(currency="EUR", metadata={"channel": "online", "country": "DE"})
        )
    )


def test_cross_border_rule_is_silent_without_a_country(make_transaction):
    assert "cross_border" not in codes(
        score_transaction(make_transaction(metadata={"channel": "online"}))
    )


def test_cross_border_rule_is_silent_for_a_currency_without_a_region(make_transaction, monkeypatch):
    monkeypatch.delitem(
        __import__("agents.protocol", fromlist=["CURRENCY_REGIONS"]).CURRENCY_REGIONS, "USD"
    )
    assert "cross_border" not in codes(score_transaction(make_transaction()))


def test_watchlist_destination_rule(make_transaction):
    assessment = score_transaction(make_transaction(destination_account="ACC-4242"))
    assert "watchlist_destination" in codes(assessment)
    assert assessment["risk_score"] == 30


def test_watchlist_matches_already_masked_destinations(make_transaction):
    assessment = score_transaction(make_transaction(destination_account="****4242"))
    assert "watchlist_destination" in codes(assessment)


# --------------------------------------------------------------------------------------
# Scoring behaviour
# --------------------------------------------------------------------------------------


def test_score_is_capped_at_one_hundred(make_transaction):
    transaction = make_transaction(
        amount="75000.00",
        timestamp="2026-03-16T02:00:00Z",
        destination_account="ACC-4242",
        metadata={"channel": "api", "country": "GB"},
    )
    assessment = score_transaction(transaction)
    assert sum(rule["points"] for rule in assessment["triggered_rules"]) > MAX_SCORE
    assert assessment["risk_score"] == MAX_SCORE
    assert assessment["risk_level"] == "high"


@pytest.mark.parametrize(
    "amount,expected_level",
    [("1500.00", "low"), ("9999.99", "medium"), ("75000.00", "high")],
)
def test_risk_levels(make_transaction, amount, expected_level):
    assert score_transaction(make_transaction(amount=amount))["risk_level"] == expected_level


def test_thresholds_are_ordered():
    assert 0 < MEDIUM_THRESHOLD < HIGH_THRESHOLD <= MAX_SCORE


def test_review_required_follows_the_reporting_threshold(make_transaction):
    # medium risk, but above 10,000 USD -> still goes to review (MO-3)
    assessment = score_transaction(make_transaction(amount="25000.00"))
    assert assessment["risk_level"] == "medium"
    assert assessment["review_required"] is True


def test_scoring_is_deterministic(make_transaction):
    transaction = make_transaction(amount="25000.00")
    assert score_transaction(transaction) == score_transaction(transaction)


def test_every_rule_in_the_table_is_callable(make_transaction):
    ctx = build_context(make_transaction())
    for rule in RULES:
        assert rule(ctx) is None or rule(ctx).points > 0


def test_usd_equivalent_is_reported(make_transaction):
    assert score_transaction(make_transaction(amount="500.00", currency="EUR"))[
        "usd_equivalent"
    ] == "545.00"


# --------------------------------------------------------------------------------------
# Message handling
# --------------------------------------------------------------------------------------


def test_process_message_forwards_to_compliance_and_never_edits_the_amount(workspace, make_message):
    incoming = make_message(target_agent="fraud_detector", amount="25000.00")
    outgoing = FraudDetector(workspace).process_message(incoming)

    assert outgoing["target_agent"] == NEXT_AGENT
    assert outgoing["data"]["amount"] == incoming["data"]["amount"]
    assert outgoing["data"]["status"] == "flagged_for_review"
    assert outgoing["data"]["fraud"]["risk_score"] == 40


def test_process_message_marks_low_risk_as_cleared(workspace, make_message):
    outgoing = FraudDetector(workspace).process_message(make_message(target_agent="fraud_detector"))
    assert outgoing["data"]["status"] == "fraud_cleared"


def test_instance_alias_matches_module_function(workspace, make_transaction):
    detector = FraudDetector(workspace)
    transaction = make_transaction(amount="25000.00")
    assert detector.score(transaction) == score_transaction(transaction)


def test_run_drains_only_messages_addressed_to_this_agent(workspace, make_message):
    workspace.write_message(workspace.output_dir, make_message(target_agent="fraud_detector"))
    workspace.write_message(
        workspace.output_dir, make_message(target_agent="settlement_processor", transaction_id="TXN2")
    )

    emitted = FraudDetector(workspace).run()

    assert len(emitted) == 1
    remaining = list(workspace.output_dir.glob("*.json"))
    assert len(remaining) == 2  # the untouched message plus the newly emitted one
