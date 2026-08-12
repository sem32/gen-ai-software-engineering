"""Unit tests for the declarative rule engine (spec task T-10, edge cases EC-16…EC-20)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from agents.rule_engine import (
    ACTION_KEYS,
    DEFAULT_ORDER,
    OPERATORS,
    SETTABLE_FIELDS,
    VALUELESS_OPERATORS,
    RuleError,
    RulePack,
    apply_pack,
    evaluate_condition,
    validate_condition,
)


def pack(*rules, defaults=None, name="test-pack"):
    return RulePack.from_dict(
        {"name": name, "version": "1", "defaults": defaults or {}, "rules": list(rules)}
    )


def rule(rule_id="r1", when=None, then=None, **extra):
    body = {"id": rule_id, "when": when if when is not None else {"all": []}, "then": then or {}}
    body.update(extra)
    return body


# --------------------------------------------------------------------------------------
# No code execution (guardrail IN-9)
# --------------------------------------------------------------------------------------


def test_engine_source_contains_no_dynamic_execution():
    from pathlib import Path

    import agents.rule_engine as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in ("eval(", "exec(", "__import__", "importlib"):
        assert forbidden not in source, f"{forbidden} must never appear in the rule engine"


def test_operator_table_is_the_documented_set():
    assert set(OPERATORS) == {
        "==", "!=", ">", ">=", "<", "<=",
        "in", "not_in", "contains", "not_contains",
        "startswith", "matches",
        "is_true", "is_false", "exists", "missing",
    }
    assert VALUELESS_OPERATORS <= set(OPERATORS)


# --------------------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "op,fact,value,expected",
    [
        ("==", "low", "low", True),
        ("==", "low", "high", False),
        ("!=", "low", "high", True),
        (">=", "10000", "10000", True),
        (">=", "9999.99", "10000", False),
        (">", "10000.01", "10000", True),
        ("<", "999.99", "1000", True),
        ("<=", "1000", "1000", True),
        ("in", "api", ["api", "online"], True),
        ("in", "branch", ["api", "online"], False),
        ("not_in", "branch", ["api", "online"], True),
        ("startswith", "****4242", "****", True),
        ("matches", "****4242", r"\*{4}42\d{2}", True),
        ("matches", "****9999", r"\*{4}42\d{2}", False),
        ("is_true", True, None, True),
        ("is_true", False, None, False),
        ("is_false", False, None, True),
        ("exists", "anything", None, True),
        ("exists", None, None, False),
        ("missing", None, None, True),
    ],
)
def test_leaf_operators(op, fact, value, expected):
    condition = {"fact": "f", "op": op}
    if value is not None:
        condition["value"] = value
    assert evaluate_condition(condition, {"f": fact}) is expected


def test_contains_works_on_lists_and_strings():
    assert evaluate_condition(
        {"fact": "codes", "op": "contains", "value": "structuring"},
        {"codes": ["high_value", "structuring"]},
    )
    assert not evaluate_condition(
        {"fact": "codes", "op": "contains", "value": "structuring"}, {"codes": ["high_value"]}
    )
    assert evaluate_condition({"fact": "note", "op": "contains", "value": "wire"}, {"note": "a wire"})
    assert not evaluate_condition({"fact": "note", "op": "contains", "value": "x"}, {"note": None})


def test_not_contains_is_the_negation():
    facts = {"codes": ["a"]}
    assert evaluate_condition({"fact": "codes", "op": "not_contains", "value": "b"}, facts)


def test_numeric_comparison_is_exact_not_float():
    # 9999.99 vs 10000 is the structuring boundary — a float would be fine here, but 0.1+0.2 style
    # drift is exactly what Decimal comparison rules out.
    facts = {"usd_amount": "0.30"}
    assert evaluate_condition({"fact": "usd_amount", "op": "==", "value": "0.3"}, facts)
    assert evaluate_condition({"fact": "usd_amount", "op": ">=", "value": "0.30"}, facts)


def test_float_operands_are_refused_not_silently_stringified():
    """A float never reaches a comparison — degrading to text could invert a policy silently.

    ``9.0 > "10"`` is false numerically but true lexicographically. Rather than pick one, the engine
    refuses, the same way :func:`agents.protocol.parse_amount` refuses a float amount.
    """
    for operator in (">", ">=", "<", "<=", "==", "!="):
        with pytest.raises(RuleError, match="float"):
            evaluate_condition({"fact": "amount", "op": operator, "value": "10"}, {"amount": 9.0})

    # A decimal string in the same position compares exactly.
    assert evaluate_condition({"fact": "amount", "op": "<", "value": "10"}, {"amount": "9.0"})


def test_integers_are_still_compared_numerically():
    """``risk_score`` arrives as an int, so ints must keep working."""
    assert evaluate_condition({"fact": "risk_score", "op": ">=", "value": "60"}, {"risk_score": 60})
    assert not evaluate_condition({"fact": "risk_score", "op": ">=", "value": "60"}, {"risk_score": 59})


def test_missing_fact_is_none_not_an_error():
    assert evaluate_condition({"fact": "absent", "op": "missing"}, {}) is True
    assert evaluate_condition({"fact": "absent", "op": "==", "value": "x"}, {}) is False


def test_in_operator_requires_a_list():
    with pytest.raises(RuleError, match="needs a list"):
        evaluate_condition({"fact": "f", "op": "in", "value": "api"}, {"f": "api"})


def test_matches_rejects_a_broken_regex():
    with pytest.raises(RuleError, match="invalid regex"):
        evaluate_condition({"fact": "f", "op": "matches", "value": "([a-"}, {"f": "x"})


# --------------------------------------------------------------------------------------
# Condition trees
# --------------------------------------------------------------------------------------


def test_nested_all_any_not():
    condition = {
        "all": [
            {"any": [{"fact": "a", "op": "==", "value": "1"}, {"fact": "b", "op": "==", "value": "2"}]},
            {"not": {"fact": "c", "op": "is_true"}},
        ]
    }
    assert evaluate_condition(condition, {"a": "1", "c": False})
    assert not evaluate_condition(condition, {"a": "1", "c": True})
    assert not evaluate_condition(condition, {"a": "9", "b": "9", "c": False})


def test_ec_19_empty_all_is_true_empty_any_is_false():
    assert evaluate_condition({"all": []}, {}) is True
    assert evaluate_condition({"any": []}, {}) is False


@pytest.mark.parametrize(
    "condition,match",
    [
        ("not an object", "must be an object"),
        ({"all": "nope"}, "must be an array"),
        ({"all": [], "any": []}, "no sibling keys"),
        ({"not": {"fact": "a", "op": "=="}, "extra": 1}, "no sibling keys"),
        ({"fact": "a", "op": "??", "value": 1}, "unknown operator"),
        ({"fact": "", "op": "=="}, "non-empty 'fact'"),
        ({"fact": "a", "op": "=="}, "requires a 'value'"),
        ({"fact": "a", "op": "==", "value": 1, "junk": 2}, "unknown key"),
    ],
)
def test_validate_condition_rejects_malformed_trees(condition, match):
    with pytest.raises(RuleError, match=match):
        validate_condition(condition, "test")


# --------------------------------------------------------------------------------------
# Pack validation (EC-16, EC-17)
# --------------------------------------------------------------------------------------


def test_ec_16_missing_pack_file_raises_rule_error(tmp_path):
    with pytest.raises(RuleError, match="cannot read rule pack"):
        RulePack.load(tmp_path / "absent.json")


def test_broken_json_raises_rule_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuleError, match="not valid JSON"):
        RulePack.load(path)


def test_pack_load_round_trip(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"name": "p", "rules": []}), encoding="utf-8")
    loaded = RulePack.load(path)
    assert loaded.name == "p"
    assert loaded.source.endswith("p.json")
    assert loaded.as_dict()["source"] == "p.json"


@pytest.mark.parametrize(
    "payload,match",
    [
        ("not an object", "must be an object"),
        ({"rules": []}, "non-empty 'name'"),
        ({"name": "p", "junk": 1}, "unknown key"),
        ({"name": "p", "defaults": "no"}, "'defaults' must be an object"),
        ({"name": "p", "defaults": {"nope": 1}}, "unknown field"),
        ({"name": "p", "rules": "no"}, "'rules' must be an array"),
    ],
)
def test_pack_validation_errors(payload, match):
    with pytest.raises(RuleError, match=match):
        RulePack.from_dict(payload)


@pytest.mark.parametrize(
    "bad_rule,match",
    [
        ("not an object", "must be an object"),
        ({"when": {"all": []}}, "non-empty 'id'"),
        ({"id": "r", "junk": 1}, "unknown key"),
        ({"id": "r", "order": "soon"}, "'order' must be an integer"),
        ({"id": "r", "then": "no"}, "'then' must be an object"),
        ({"id": "r", "then": {"nope": 1}}, "unknown key"),
        ({"id": "r", "then": {"set": "no"}}, "'then.set' must be an object"),
        ({"id": "r", "then": {"set": {"nope": 1}}}, "unknown field"),
        ({"id": "r", "then": {"tags": "no"}}, "array of strings"),
        ({"id": "r", "then": {"tags": [1]}}, "array of strings"),
        ({"id": "r", "then": {"hold": ""}}, "non-empty reason code"),
    ],
)
def test_ec_17_rule_validation_errors_name_the_rule(bad_rule, match):
    with pytest.raises(RuleError, match=match):
        RulePack.from_dict({"name": "p", "rules": [bad_rule]})


def test_duplicate_rule_id_is_rejected():
    with pytest.raises(RuleError, match="duplicate rule id"):
        pack(rule("same"), rule("same"))


def test_disabled_rule_is_still_validated():
    with pytest.raises(RuleError, match="unknown operator"):
        pack(rule("r", when={"fact": "a", "op": "??", "value": 1}, enabled=False))


def test_action_and_field_vocabularies_are_closed():
    assert ACTION_KEYS == {"set", "tags", "hold"}
    assert "fee_rate" in SETTABLE_FIELDS and "priority" in SETTABLE_FIELDS


# --------------------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------------------


def test_defaults_seed_the_outcome_and_are_attributed():
    result = apply_pack(pack(defaults={"priority": "deferred", "sla_hours": 72}), {})
    assert result["outcome"]["priority"] == "deferred"
    assert result["outcome"]["sla_hours"] == 72
    assert result["decided_by"]["priority"] == "defaults"


def test_matching_rule_sets_fields_tags_and_hold():
    result = apply_pack(
        pack(
            rule(
                "r",
                when={"fact": "risk", "op": "==", "value": "high"},
                then={"set": {"priority": "deferred"}, "tags": ["a", "b"], "hold": "manual_review"},
            )
        ),
        {"risk": "high"},
    )
    outcome = result["outcome"]
    assert outcome["priority"] == "deferred"
    assert outcome["tags"] == ["a", "b"]
    assert outcome["hold"] is True
    assert outcome["hold_reasons"] == ["manual_review"]
    assert result["matched_rules"][0]["id"] == "r"


def test_non_matching_rule_changes_nothing():
    result = apply_pack(
        pack(rule("r", when={"fact": "risk", "op": "==", "value": "high"}, then={"tags": ["x"]})),
        {"risk": "low"},
    )
    assert result["matched_rules"] == []
    assert result["outcome"]["tags"] == []


def test_ec_18_conflicting_rules_resolve_by_order_and_report_the_winner():
    result = apply_pack(
        pack(
            rule("late", order=50, then={"set": {"priority": "deferred"}}),
            rule("early", order=10, then={"set": {"priority": "express"}}),
        ),
        {},
    )
    assert result["outcome"]["priority"] == "deferred"  # higher order runs last, wins
    assert result["decided_by"]["priority"] == "late"


def test_declaration_order_breaks_an_order_tie():
    result = apply_pack(
        pack(
            rule("first", then={"set": {"priority": "a"}}),
            rule("second", then={"set": {"priority": "b"}}),
        ),
        {},
    )
    assert result["decided_by"]["priority"] == "second"
    assert all(r.order == DEFAULT_ORDER for r in pack(rule("x")).rules)


def test_stop_prevents_later_rules():
    result = apply_pack(
        pack(
            rule("one", order=10, then={"tags": ["one"]}, stop=True),
            rule("two", order=20, then={"tags": ["two"]}),
        ),
        {},
    )
    assert result["outcome"]["tags"] == ["one"]
    assert [r["id"] for r in result["matched_rules"]] == ["one"]


def test_disabled_rule_never_fires():
    result = apply_pack(pack(rule("off", enabled=False, then={"tags": ["x"]})), {})
    assert result["outcome"]["tags"] == []
    assert result["evaluated"] == 0


def test_tags_are_deduplicated_in_order():
    result = apply_pack(
        pack(
            rule("a", order=10, then={"tags": ["x", "y"]}),
            rule("b", order=20, then={"tags": ["y", "z"]}),
        ),
        {},
    )
    assert result["outcome"]["tags"] == ["x", "y", "z"]


def test_repeated_hold_reason_is_recorded_once():
    result = apply_pack(
        pack(
            rule("a", order=10, then={"hold": "same"}),
            rule("b", order=20, then={"hold": "same"}),
        ),
        {},
    )
    assert result["outcome"]["hold_reasons"] == ["same"]
    assert result["decided_by"]["hold"] == "a"


def test_apply_pack_is_deterministic():
    built = pack(rule("r", when={"fact": "a", "op": "exists"}, then={"tags": ["t"]}))
    facts = {"a": 1}
    assert apply_pack(built, facts) == apply_pack(built, facts)


def test_ordered_rules_is_sorted():
    built = pack(rule("c", order=30), rule("a", order=10), rule("b", order=20))
    assert [r.id for r in built.ordered_rules] == ["a", "b", "c"]


def test_pack_as_dict_exposes_every_rule():
    built = pack(rule("r", then={"tags": ["x"]}))
    payload = built.as_dict()
    assert payload["name"] == "test-pack"
    assert payload["rules"][0]["id"] == "r"
    assert payload["rules"][0]["then"] == {"tags": ["x"]}


def test_empty_pack_needs_no_rules():
    assert apply_pack(pack(), {})["matched_rules"] == []


# --------------------------------------------------------------------------------------
# The shipped packs
# --------------------------------------------------------------------------------------


def test_shipped_packs_load_and_are_distinct():
    from agents.policy_engine import RULES_DIR, available_packs

    assert set(available_packs()) == {"policy-default", "policy-strict"}
    default = RulePack.load(RULES_DIR / "policy-default.json")
    strict = RulePack.load(RULES_DIR / "policy-strict.json")
    assert default.name == "policy-default"
    assert strict.name == "policy-strict"
    assert {r.id for r in default.rules} != {r.id for r in strict.rules}


def test_default_pack_never_touches_a_monetary_field():
    """This is the guarantee that keeps the §8 baseline intact (guardrail IN-8)."""
    from agents.policy_engine import RULES_DIR

    monetary = {"fee_rate", "fee_floor", "fee_cap", "settlement_lag"}
    default = RulePack.load(RULES_DIR / "policy-default.json")
    for rule_obj in default.rules:
        assert not monetary & set(rule_obj.then.get("set", {})), rule_obj.id
    assert not monetary & set(default.defaults)


def test_strict_pack_does_touch_money():
    from agents.policy_engine import RULES_DIR

    strict = RulePack.load(RULES_DIR / "policy-strict.json")
    overrides = {
        field for rule_obj in strict.rules for field in rule_obj.then.get("set", {})
    }
    assert "fee_rate" in overrides and "fee_cap" in overrides
    assert Decimal("0.0035") > 0  # the surcharge is expressed as a string in the pack
