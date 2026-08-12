"""Declarative rule engine (spec task T-10, guardrail IN-9).

Rules are **data, never code**. There is no ``eval``, no ``exec`` and no importing a module named in
a configuration file — a condition is a small JSON structure evaluated by an explicit operator table.
A pack that cannot be fully understood is rejected at *load* time, naming the rule and the field, so
a typo can never silently disable a control at decision time.

The engine knows nothing about banking; it maps a flat dictionary of facts onto an outcome dictionary.
:mod:`agents.policy_engine` is what gives it meaning.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable


class RuleError(ValueError):
    """A rule pack is malformed, unreadable, or references something the engine does not know."""


# --------------------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------------------


def _as_decimal(value: Any) -> Decimal | None:
    """Return ``value`` as a Decimal when it losslessly is one, else ``None``.

    ``float`` is deliberately excluded: a rule pack that wants a number writes it as a string
    (guardrail IN-1), and accepting a float here would let one into a money path.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or isinstance(value, float):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str) and value.strip():
        try:
            candidate = Decimal(value.strip())
        except InvalidOperation:
            return None
        return candidate if candidate.is_finite() else None
    return None


def _reject_float(*values: Any) -> None:
    """Refuse ``float`` operands outright.

    A float is not exact, and silently degrading to a *text* comparison would be worse than an error:
    ``9.0 > "10"`` is false numerically but true lexicographically, so a policy could invert without
    anyone noticing. Rule packs write numbers as strings, and :func:`agents.policy_engine.build_facts`
    only ever emits strings and ints — so this guard is unreachable in normal use and loud when it is
    not (mirrors :func:`agents.protocol.parse_amount`).
    """
    for value in values:
        if isinstance(value, float):
            raise RuleError(
                f"refusing to compare the float {value!r}: write numbers as strings so they stay exact"
            )


def _compare(fact: Any, expected: Any, numeric: Callable[[Decimal, Decimal], bool],
             textual: Callable[[Any, Any], bool]) -> bool:
    """Compare numerically when both sides are exact numbers, textually otherwise."""
    _reject_float(fact, expected)
    left, right = _as_decimal(fact), _as_decimal(expected)
    if left is not None and right is not None:
        return numeric(left, right)
    if fact is None or expected is None:
        return False
    return textual(str(fact), str(expected))


def _op_eq(fact: Any, expected: Any) -> bool:
    _reject_float(fact, expected)
    left, right = _as_decimal(fact), _as_decimal(expected)
    if left is not None and right is not None:
        return left == right
    return fact == expected


def _op_in(fact: Any, expected: Any) -> bool:
    if not isinstance(expected, (list, tuple, set)):
        raise RuleError(f"operator 'in' needs a list value, got {type(expected).__name__}")
    return any(_op_eq(fact, candidate) for candidate in expected)


def _op_contains(fact: Any, expected: Any) -> bool:
    if isinstance(fact, (list, tuple, set)):
        return any(_op_eq(item, expected) for item in fact)
    if fact is None:
        return False
    return str(expected) in str(fact)


def _op_matches(fact: Any, expected: Any) -> bool:
    if fact is None:
        return False
    try:
        pattern = re.compile(str(expected))
    except re.error as exc:
        raise RuleError(f"operator 'matches' got an invalid regex {expected!r}: {exc}") from exc
    return pattern.fullmatch(str(fact)) is not None


#: The complete operator table. A test asserts this exact key set, so adding an operator is a
#: deliberate, reviewed act rather than an accident.
OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": _op_eq,
    "!=": lambda fact, expected: not _op_eq(fact, expected),
    ">": lambda f, e: _compare(f, e, lambda a, b: a > b, lambda a, b: a > b),
    ">=": lambda f, e: _compare(f, e, lambda a, b: a >= b, lambda a, b: a >= b),
    "<": lambda f, e: _compare(f, e, lambda a, b: a < b, lambda a, b: a < b),
    "<=": lambda f, e: _compare(f, e, lambda a, b: a <= b, lambda a, b: a <= b),
    "in": _op_in,
    "not_in": lambda fact, expected: not _op_in(fact, expected),
    "contains": _op_contains,
    "not_contains": lambda fact, expected: not _op_contains(fact, expected),
    "startswith": lambda fact, expected: fact is not None
    and str(fact).startswith(str(expected)),
    "matches": _op_matches,
    "is_true": lambda fact, _expected: fact is True,
    "is_false": lambda fact, _expected: fact is False,
    "exists": lambda fact, _expected: fact is not None,
    "missing": lambda fact, _expected: fact is None,
}

#: Operators that ignore ``value`` — a pack may omit it for these.
VALUELESS_OPERATORS = frozenset({"is_true", "is_false", "exists", "missing"})

# --------------------------------------------------------------------------------------
# Outcome vocabulary
# --------------------------------------------------------------------------------------

#: Scalar fields a rule may assign through ``then.set``.
SETTABLE_FIELDS = frozenset(
    {
        "priority",
        "sla_hours",
        "dual_approval_required",
        "fee_rate",
        "fee_floor",
        "fee_cap",
        "settlement_lag",
    }
)

#: Keys allowed inside ``then``.
ACTION_KEYS = frozenset({"set", "tags", "hold"})

#: Keys allowed on a rule.
RULE_KEYS = frozenset({"id", "description", "enabled", "order", "when", "then", "stop"})

#: Keys allowed on a pack.
PACK_KEYS = frozenset({"name", "version", "description", "defaults", "rules"})

DEFAULT_ORDER = 100

# --------------------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """One validated rule."""

    id: str
    description: str
    enabled: bool
    order: int
    when: dict[str, Any]
    then: dict[str, Any]
    stop: bool
    index: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "enabled": self.enabled,
            "order": self.order,
            "when": self.when,
            "then": self.then,
            "stop": self.stop,
        }


@dataclass(frozen=True)
class RulePack:
    """A validated pack. Construction is the only place validation happens."""

    name: str
    version: str
    description: str
    defaults: dict[str, Any]
    rules: tuple[Rule, ...]
    source: str | None = field(default=None)

    # -- construction ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | str) -> "RulePack":
        """Read, parse and validate a pack in one step.

        A missing or unreadable file raises :class:`RuleError` rather than leaking an OS error (and
        therefore a filesystem path) into an API response — see guardrail IN-10.
        """
        pack_path = Path(path)
        try:
            raw = pack_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuleError(f"cannot read rule pack {pack_path.name!r}: {exc.strerror}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuleError(f"rule pack {pack_path.name!r} is not valid JSON: {exc.msg}") from exc
        return cls.from_dict(payload, source=str(pack_path))

    @classmethod
    def from_dict(cls, payload: Any, *, source: str | None = None) -> "RulePack":
        if not isinstance(payload, dict):
            raise RuleError(f"rule pack must be an object, got {type(payload).__name__}")
        _reject_unknown_keys(payload, PACK_KEYS, "rule pack")

        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise RuleError("rule pack requires a non-empty 'name'")

        defaults = payload.get("defaults", {})
        if not isinstance(defaults, dict):
            raise RuleError(f"pack {name!r}: 'defaults' must be an object")
        unknown = set(defaults) - SETTABLE_FIELDS
        if unknown:
            raise RuleError(
                f"pack {name!r}: 'defaults' has unknown field(s) {sorted(unknown)}; "
                f"allowed: {sorted(SETTABLE_FIELDS)}"
            )

        raw_rules = payload.get("rules", [])
        if not isinstance(raw_rules, list):
            raise RuleError(f"pack {name!r}: 'rules' must be an array")

        rules: list[Rule] = []
        seen: set[str] = set()
        for index, raw_rule in enumerate(raw_rules):
            rule = _parse_rule(raw_rule, index, name)
            if rule.id in seen:
                raise RuleError(f"pack {name!r}: duplicate rule id {rule.id!r}")
            seen.add(rule.id)
            rules.append(rule)

        return cls(
            name=name,
            version=str(payload.get("version", "0")),
            description=str(payload.get("description", "")),
            defaults=dict(defaults),
            rules=tuple(rules),
            source=source,
        )

    # -- introspection -----------------------------------------------------------------

    @property
    def ordered_rules(self) -> tuple[Rule, ...]:
        """Rules in evaluation order: ``order`` first, declaration order as the tie-break."""
        return tuple(sorted(self.rules, key=lambda rule: (rule.order, rule.index)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "source": Path(self.source).name if self.source else None,
            "defaults": dict(self.defaults),
            "rules": [rule.as_dict() for rule in self.rules],
        }


def _reject_unknown_keys(payload: dict[str, Any], allowed: Iterable[str], where: str) -> None:
    unknown = set(payload) - set(allowed)
    if unknown:
        raise RuleError(f"{where} has unknown key(s) {sorted(unknown)}; allowed: {sorted(allowed)}")


def _parse_rule(raw: Any, index: int, pack_name: str) -> Rule:
    label = f"pack {pack_name!r}, rule #{index}"
    if not isinstance(raw, dict):
        raise RuleError(f"{label}: must be an object, got {type(raw).__name__}")
    _reject_unknown_keys(raw, RULE_KEYS, label)

    rule_id = raw.get("id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise RuleError(f"{label}: requires a non-empty 'id'")
    label = f"pack {pack_name!r}, rule {rule_id!r}"

    order = raw.get("order", DEFAULT_ORDER)
    if isinstance(order, bool) or not isinstance(order, int):
        raise RuleError(f"{label}: 'order' must be an integer")

    when = raw.get("when", {"all": []})
    validate_condition(when, label)

    then = raw.get("then", {})
    if not isinstance(then, dict):
        raise RuleError(f"{label}: 'then' must be an object")
    _reject_unknown_keys(then, ACTION_KEYS, f"{label} action")

    assignments = then.get("set", {})
    if not isinstance(assignments, dict):
        raise RuleError(f"{label}: 'then.set' must be an object")
    unknown = set(assignments) - SETTABLE_FIELDS
    if unknown:
        raise RuleError(
            f"{label}: 'then.set' has unknown field(s) {sorted(unknown)}; "
            f"allowed: {sorted(SETTABLE_FIELDS)}"
        )

    tags = then.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise RuleError(f"{label}: 'then.tags' must be an array of strings")

    hold = then.get("hold")
    if hold is not None and (not isinstance(hold, str) or not hold.strip()):
        raise RuleError(f"{label}: 'then.hold' must be a non-empty reason code")

    return Rule(
        id=rule_id,
        description=str(raw.get("description", "")),
        enabled=bool(raw.get("enabled", True)),
        order=order,
        when=when,
        then=then,
        stop=bool(raw.get("stop", False)),
        index=index,
    )


# --------------------------------------------------------------------------------------
# Conditions
# --------------------------------------------------------------------------------------


def validate_condition(condition: Any, label: str) -> None:
    """Validate a condition tree at load time so evaluation cannot fail on a typo."""
    if not isinstance(condition, dict):
        raise RuleError(f"{label}: condition must be an object, got {type(condition).__name__}")

    if "all" in condition or "any" in condition:
        key = "all" if "all" in condition else "any"
        if set(condition) != {key}:
            raise RuleError(f"{label}: a {key!r} condition takes no sibling keys")
        children = condition[key]
        if not isinstance(children, list):
            raise RuleError(f"{label}: {key!r} must be an array of conditions")
        for child in children:
            validate_condition(child, label)
        return

    if "not" in condition:
        if set(condition) != {"not"}:
            raise RuleError(f"{label}: a 'not' condition takes no sibling keys")
        validate_condition(condition["not"], label)
        return

    unknown = set(condition) - {"fact", "op", "value"}
    if unknown:
        raise RuleError(f"{label}: condition has unknown key(s) {sorted(unknown)}")
    fact = condition.get("fact")
    if not isinstance(fact, str) or not fact.strip():
        raise RuleError(f"{label}: condition requires a non-empty 'fact'")
    operator = condition.get("op")
    if operator not in OPERATORS:
        raise RuleError(
            f"{label}: unknown operator {operator!r} on fact {fact!r}; "
            f"known operators: {sorted(OPERATORS)}"
        )
    if operator not in VALUELESS_OPERATORS and "value" not in condition:
        raise RuleError(f"{label}: operator {operator!r} on fact {fact!r} requires a 'value'")


def evaluate_condition(condition: dict[str, Any], facts: dict[str, Any]) -> bool:
    """Evaluate a validated condition tree against a flat fact dictionary.

    ``all`` of nothing is true and ``any`` of nothing is false (edge case EC-19) — the arithmetic
    identities, chosen explicitly because guessing here would silently invert a policy.
    """
    if "all" in condition:
        return all(evaluate_condition(child, facts) for child in condition["all"])
    if "any" in condition:
        return any(evaluate_condition(child, facts) for child in condition["any"])
    if "not" in condition:
        return not evaluate_condition(condition["not"], facts)

    operator = OPERATORS[condition["op"]]
    return bool(operator(facts.get(condition["fact"]), condition.get("value")))


# --------------------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------------------


def apply_pack(pack: RulePack, facts: dict[str, Any]) -> dict[str, Any]:
    """Apply every enabled rule to ``facts`` and return the merged outcome.

    Pure: the same pack and the same facts always produce an equal dictionary.
    """
    outcome: dict[str, Any] = {
        "priority": "standard",
        "sla_hours": 24,
        "dual_approval_required": False,
        "fee_rate": None,
        "fee_floor": None,
        "fee_cap": None,
        "settlement_lag": None,
        "tags": [],
        "hold": False,
        "hold_reasons": [],
    }
    decided_by: dict[str, str] = {}
    for name, value in pack.defaults.items():
        outcome[name] = value
        decided_by[name] = "defaults"

    matched: list[dict[str, Any]] = []
    evaluated = 0

    for rule in pack.ordered_rules:
        if not rule.enabled:
            continue
        evaluated += 1
        if not evaluate_condition(rule.when, facts):
            continue

        for name, value in rule.then.get("set", {}).items():
            outcome[name] = value
            decided_by[name] = rule.id

        for tag in rule.then.get("tags", []):
            if tag not in outcome["tags"]:
                outcome["tags"].append(tag)

        hold_reason = rule.then.get("hold")
        if hold_reason:
            outcome["hold"] = True
            if hold_reason not in outcome["hold_reasons"]:
                outcome["hold_reasons"].append(hold_reason)
            decided_by.setdefault("hold", rule.id)

        matched.append(
            {
                "id": rule.id,
                "description": rule.description,
                "order": rule.order,
                "actions": rule.then,
            }
        )

        if rule.stop:
            break

    return {
        "pack": {"name": pack.name, "version": pack.version},
        "outcome": outcome,
        "matched_rules": matched,
        "decided_by": decided_by,
        "evaluated": evaluated,
    }
