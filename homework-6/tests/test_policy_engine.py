"""Unit tests for the policy engine agent (spec task T-11, §8b, edge cases EC-16/EC-20/EC-21)."""

from __future__ import annotations

import json

import pytest

from agents.compliance_checker import screen_transaction
from agents.fraud_detector import score_transaction
from agents.policy_engine import (
    DEFAULT_PACK_NAME,
    PACK_ENV_VAR,
    PolicyEngine,
    available_packs,
    build_facts,
    pack_path_for,
    resolve_pack,
)
from agents.protocol import TERMINAL_TARGET
from agents.settlement_processor import settle_transaction
from conftest import SAMPLE_PATH
from integrator import run_pipeline


@pytest.fixture
def screened(make_transaction):
    """A transaction as the policy engine receives it: fraud-scored and compliance-cleared."""

    def _screened(**overrides):
        transaction = make_transaction(**overrides)
        transaction["fraud"] = score_transaction(transaction)
        transaction["compliance"] = screen_transaction(transaction)
        transaction["status"] = "compliance_cleared"
        return transaction

    return _screened


# --------------------------------------------------------------------------------------
# Pack resolution
# --------------------------------------------------------------------------------------


def test_available_packs_lists_the_shipped_ones():
    assert set(available_packs()) == {"policy-default", "policy-strict"}


@pytest.mark.parametrize(
    "spec,expected_stem",
    [(None, DEFAULT_PACK_NAME), ("policy-strict", "policy-strict"), ("policy-strict.json", "policy-strict")],
)
def test_pack_path_for_accepts_names_and_filenames(spec, expected_stem):
    assert pack_path_for(spec).stem == expected_stem


def test_pack_path_for_accepts_an_absolute_path(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text('{"name":"custom","rules":[]}', encoding="utf-8")
    assert pack_path_for(path) == path


def test_resolve_pack_defaults_to_the_default_pack():
    assert resolve_pack().name == DEFAULT_PACK_NAME


def test_env_var_selects_the_pack(monkeypatch):
    monkeypatch.setenv(PACK_ENV_VAR, "policy-strict")
    assert resolve_pack().name == "policy-strict"


def test_explicit_argument_beats_the_env_var(monkeypatch):
    monkeypatch.setenv(PACK_ENV_VAR, "policy-strict")
    assert resolve_pack("policy-default").name == "policy-default"


def test_resolve_pack_accepts_a_loaded_pack():
    pack = resolve_pack("policy-strict")
    assert resolve_pack(pack) is pack


# --------------------------------------------------------------------------------------
# Facts (spec §3.8)
# --------------------------------------------------------------------------------------


def test_build_facts_exposes_every_documented_fact(screened):
    facts = build_facts(screened())
    expected = {
        "transaction_id", "transaction_type", "currency", "amount", "usd_amount", "channel",
        "country", "hour_utc", "weekday", "source_account", "destination_account", "status",
        "risk_score", "risk_level", "review_required", "fraud_rules", "ctr_required",
        "compliance_decision", "compliance_holds", "is_cross_border",
    }
    assert set(facts) == expected


def test_facts_come_from_the_transaction_not_the_clock(screened):
    facts = build_facts(screened(timestamp="2026-03-16T02:47:00Z"))
    assert facts["hour_utc"] == 2
    assert facts["weekday"] == 0  # 2026-03-16 is a Monday


def test_fraud_rule_codes_are_flattened(screened):
    facts = build_facts(screened(amount="9999.99"))
    assert "structuring" in facts["fraud_rules"]


def test_cross_border_is_derived(screened):
    domestic = build_facts(screened(metadata={"channel": "online", "country": "US"}))
    foreign = build_facts(screened(metadata={"channel": "online", "country": "GB"}))
    assert domestic["is_cross_border"] is False
    assert foreign["is_cross_border"] is True


# --------------------------------------------------------------------------------------
# The agent
# --------------------------------------------------------------------------------------


def test_default_pack_approves_and_routes_to_settlement(workspace, make_message, screened):
    message = make_message(target_agent="policy_engine")
    message["data"] = screened()
    outgoing = PolicyEngine(workspace).process_message(message)

    assert outgoing["target_agent"] == "settlement_processor"
    assert outgoing["data"]["status"] == "policy_cleared"
    policy = outgoing["data"]["policy"]
    assert policy["decision"] == "approved"
    assert policy["pack"]["name"] == "policy-default"
    assert "fee_rate" not in policy  # the default pack never touches money


def test_default_pack_assigns_routing_metadata(workspace, screened):
    policy = PolicyEngine(workspace).apply(screened(amount="25000.00", transaction_type="wire_transfer"))
    assert policy["priority"] == "deferred"
    assert policy["dual_approval_required"] is True
    assert {"wire", "ctr-filed", "manual-check"} <= set(policy["tags"])
    assert policy["decided_by"]["priority"] == "elevated_risk_review"


def test_strict_pack_holds_a_structuring_candidate(workspace, make_message, screened):
    message = make_message(target_agent="policy_engine")
    message["data"] = screened(amount="9999.99")
    outgoing = PolicyEngine(workspace, pack="policy-strict").process_message(message)

    assert outgoing["target_agent"] == TERMINAL_TARGET
    assert outgoing["data"]["status"] == "held"
    assert outgoing["data"]["hold_reason"] == "structuring_manual_review"


def test_strict_pack_applies_the_surcharge(workspace, screened):
    policy = PolicyEngine(workspace, pack="policy-strict").apply(screened(amount="25000.00"))
    assert policy["fee_rate"] == "0.0035"
    assert policy["fee_cap"] == "100.00"
    assert policy["decided_by"]["fee_rate"] == "strict_high_value_surcharge"


def test_ec_16_unloadable_pack_fails_closed(workspace, make_message, screened, tmp_path):
    message = make_message(target_agent="policy_engine")
    message["data"] = screened()
    agent = PolicyEngine(workspace, pack=tmp_path / "missing.json")

    outgoing = agent.process_message(message)

    assert outgoing["data"]["status"] == "held"
    assert outgoing["data"]["policy"]["hold_reasons"] == ["policy_pack_unavailable"]
    assert agent.pack_name == "unavailable"


def test_unbuildable_facts_fail_closed(workspace, make_message, screened):
    message = make_message(target_agent="policy_engine")
    data = screened()
    data["amount"] = "not a number"
    message["data"] = data

    outgoing = PolicyEngine(workspace).process_message(message)

    assert outgoing["data"]["status"] == "held"
    assert outgoing["data"]["policy"]["hold_reasons"] == ["policy_facts_unavailable"]


def test_agent_never_edits_the_amount(workspace, make_message, screened):
    message = make_message(target_agent="policy_engine")
    message["data"] = screened(amount="9999.99")
    outgoing = PolicyEngine(workspace, pack="policy-strict").process_message(message)
    assert outgoing["data"]["amount"] == "9999.99"


def test_run_drains_the_inbox(workspace, make_message, screened):
    message = make_message(target_agent="policy_engine")
    message["data"] = screened()
    workspace.write_message(workspace.output_dir, message)

    emitted = PolicyEngine(workspace).run()

    assert len(emitted) == 1
    assert emitted[0]["source_agent"] == "policy_engine"


# --------------------------------------------------------------------------------------
# Settlement honouring the overrides (spec task T-12, EC-20/EC-21)
# --------------------------------------------------------------------------------------


def test_overrides_change_the_fee(screened):
    transaction = screened(amount="25000.00")
    transaction["policy"] = {
        "fee_rate": "0.0035",
        "fee_cap": "100.00",
        "decided_by": {"fee_rate": "strict_high_value_surcharge"},
    }
    settlement = settle_transaction(transaction)
    assert settlement["fee"] == "87.50"
    assert settlement["net_amount"] == "24912.50"
    assert settlement["fee_source"] == "policy:strict_high_value_surcharge"


def test_no_policy_section_reproduces_the_default_fee(screened):
    plain = settle_transaction(screened(amount="25000.00"))
    assert plain["fee"] == "25.00"
    assert plain["fee_source"] == "default"
    assert plain["lag_source"] == "default"


def test_ec_21_settlement_lag_override_of_zero(screened):
    transaction = screened()
    transaction["policy"] = {"settlement_lag": 0, "decided_by": {"settlement_lag": "same_day"}}
    settlement = settle_transaction(transaction)
    assert settlement["value_date"] == "2026-03-16"  # the transaction date itself
    assert settlement["business_day_lag"] == 0
    assert settlement["lag_source"] == "policy:same_day"


def test_lag_source_without_attribution(screened):
    transaction = screened()
    transaction["policy"] = {"settlement_lag": 3}
    assert settle_transaction(transaction)["lag_source"] == "policy"


@pytest.mark.parametrize("override", [{"fee_rate": "-0.01"}, {"fee_cap": "-1"}, {"fee_floor": "-1"}])
def test_ec_20_negative_override_is_rejected(screened, override):
    from agents.protocol import MoneyError

    transaction = screened()
    transaction["policy"] = override
    with pytest.raises(MoneyError, match="must not be negative"):
        settle_transaction(transaction)


def test_unparseable_override_is_rejected(screened):
    from agents.protocol import MoneyError

    transaction = screened()
    transaction["policy"] = {"fee_rate": "cheap"}
    with pytest.raises(MoneyError):
        settle_transaction(transaction)


def test_ledger_invariant_holds_under_overrides(screened):
    from agents.protocol import parse_amount

    transaction = screened(amount="25000.00")
    transaction["policy"] = {"fee_rate": "0.0035", "fee_cap": "100.00"}
    settlement = settle_transaction(transaction)
    assert parse_amount(settlement["fee"]) + parse_amount(settlement["net_amount"]) == parse_amount(
        settlement["gross_amount"]
    )


# --------------------------------------------------------------------------------------
# §8b — the whole sample under the strict pack
# --------------------------------------------------------------------------------------

EXPECTED_STRICT = {
    "TXN001": ("settled", None),
    "TXN002": ("settled", "87.50"),
    "TXN003": ("held", None),
    "TXN004": ("held", None),
    "TXN005": ("held", None),
    "TXN006": ("rejected", None),
    "TXN007": ("rejected", None),
    "TXN008": ("settled", None),
}


@pytest.fixture(scope="module")
def strict_run(tmp_path_factory):
    shared = tmp_path_factory.mktemp("strict") / "shared"
    return run_pipeline(SAMPLE_PATH, shared, verbose=False, rules="policy-strict"), shared


def test_8b_totals(strict_run):
    summary, _ = strict_run
    assert summary["by_status"] == {"held": 3, "rejected": 2, "settled": 3}
    assert summary["reconciled"] is True
    assert summary["rule_packs"] == {"policy-strict": 5}


@pytest.mark.parametrize("transaction_id", sorted(EXPECTED_STRICT))
def test_8b_per_transaction(strict_run, transaction_id):
    summary, shared = strict_run
    row = next(r for r in summary["transactions"] if r["transaction_id"] == transaction_id)
    expected_status, expected_fee = EXPECTED_STRICT[transaction_id]
    assert row["status"] == expected_status

    if expected_fee is not None:
        record = json.loads(
            next(shared.glob(f"results/{transaction_id}-*.json")).read_text(encoding="utf-8")
        )
        assert record["data"]["settlement"]["fee"] == expected_fee


def test_switching_packs_needs_no_code_change(tmp_path):
    """The point of MO-7: same code, same input, different data, different outcome."""
    default = run_pipeline(SAMPLE_PATH, tmp_path / "d", verbose=False, rules="policy-default")
    strict = run_pipeline(SAMPLE_PATH, tmp_path / "s", verbose=False, rules="policy-strict")
    assert default["by_status"] == {"held": 1, "rejected": 2, "settled": 5}
    assert strict["by_status"] == {"held": 3, "rejected": 2, "settled": 3}
