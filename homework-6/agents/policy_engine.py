"""Agent 6 of the runtime pipeline — configurable business policy (spec task T-11).

Consumes compliance-cleared transactions and applies a **rule pack loaded from JSON**. Nothing this
agent decides is hardcoded: swap the pack and the pipeline behaves differently with no code change
(objective MO-7). A pack that will not load is a hold, never a silent approval (guardrail IN-3).

Sits between :mod:`agents.compliance_checker` and :mod:`agents.settlement_processor`. It attaches a
``policy`` section and never edits ``amount`` or another agent's section (guardrail IN-4).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - only when run as a script (PEP 366)
    import sys as _sys

    _sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "agents"

from .base import BaseAgent
from .protocol import CURRENCY_REGIONS, MoneyError, parse_amount, parse_timestamp, usd_equivalent
from .rule_engine import RuleError, RulePack, apply_pack

NEXT_AGENT = "settlement_processor"

#: Directory holding the shipped packs.
RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
DEFAULT_PACK_NAME = "policy-default"
DEFAULT_PACK_PATH = RULES_DIR / f"{DEFAULT_PACK_NAME}.json"

#: Environment variable selecting a pack when no explicit one is given.
PACK_ENV_VAR = "HW6_POLICY_RULES"

#: Hold reason used when the pack itself is unusable — fail closed.
PACK_UNAVAILABLE = "policy_pack_unavailable"


def pack_path_for(spec: str | Path | None) -> Path:
    """Resolve a pack specification to a path.

    Accepts a bare pack name (``"policy-strict"``), a file name (``"policy-strict.json"``) or any
    path. A bare name is looked up in :data:`RULES_DIR`, so callers never hardcode a path.
    """
    if spec is None:
        return DEFAULT_PACK_PATH
    candidate = Path(spec)
    if candidate.suffix == ".json" and (candidate.is_absolute() or candidate.exists()):
        return candidate
    if candidate.suffix == ".json":
        return RULES_DIR / candidate.name
    return RULES_DIR / f"{candidate.name}.json"


def resolve_pack(spec: str | Path | RulePack | None = None) -> RulePack:
    """Load the pack named by ``spec``, then ``HW6_POLICY_RULES``, then the default pack."""
    if isinstance(spec, RulePack):
        return spec
    if spec is None:
        spec = os.environ.get(PACK_ENV_VAR) or None
    return RulePack.load(pack_path_for(spec))


def available_packs() -> list[str]:
    """Names of the packs shipped in :data:`RULES_DIR`, for the API and the CLI."""
    if not RULES_DIR.is_dir():
        return []
    return sorted(path.stem for path in RULES_DIR.glob("*.json"))


# --------------------------------------------------------------------------------------
# Facts (pure — guardrail IN-6)
# --------------------------------------------------------------------------------------


def build_facts(transaction: dict[str, Any]) -> dict[str, Any]:
    """Flatten the accumulated payload into the fact dictionary rules see (spec §3.8).

    Pure: ``hour_utc`` and ``weekday`` come from the transaction's own timestamp, never the clock.
    """
    fraud = transaction.get("fraud") or {}
    compliance = transaction.get("compliance") or {}
    metadata = transaction.get("metadata") or {}

    currency = str(transaction.get("currency", ""))
    amount = parse_amount(transaction.get("amount"))
    country = metadata.get("country")
    region = CURRENCY_REGIONS.get(currency)

    submitted_at = parse_timestamp(transaction["timestamp"])

    return {
        "transaction_id": transaction.get("transaction_id"),
        "transaction_type": transaction.get("transaction_type"),
        "currency": currency,
        "amount": str(amount),
        "usd_amount": str(usd_equivalent(amount, currency)),
        "channel": metadata.get("channel"),
        "country": country,
        "hour_utc": submitted_at.hour,
        "weekday": submitted_at.weekday(),
        "source_account": transaction.get("source_account"),
        "destination_account": transaction.get("destination_account"),
        "status": transaction.get("status"),
        "risk_score": fraud.get("risk_score"),
        "risk_level": fraud.get("risk_level"),
        "review_required": bool(fraud.get("review_required")),
        "fraud_rules": [rule.get("code") for rule in fraud.get("triggered_rules", [])],
        "ctr_required": bool(compliance.get("ctr_required")),
        "compliance_decision": compliance.get("decision"),
        "compliance_holds": list(compliance.get("hold_reasons") or []),
        "is_cross_border": bool(region and country and country not in region),
    }


# --------------------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------------------


class PolicyEngine(BaseAgent):
    """Applies a configurable rule pack and routes onward to settlement."""

    name = "policy_engine"
    inbox = "output"

    def __init__(self, workspace, audit=None, pack: str | Path | RulePack | None = None) -> None:
        super().__init__(workspace, audit)
        self._pack_spec = pack
        self._pack: RulePack | None = None
        self._pack_error: str | None = None

    @property
    def pack(self) -> RulePack | None:
        """The active pack, loaded lazily so a bad pack becomes a hold rather than a crash."""
        if self._pack is None and self._pack_error is None:
            try:
                self._pack = resolve_pack(self._pack_spec)
            except RuleError as exc:
                self._pack_error = str(exc)
        return self._pack

    @property
    def pack_name(self) -> str:
        pack = self.pack
        return pack.name if pack else "unavailable"

    def apply(self, transaction: dict[str, Any]) -> dict[str, Any]:
        """Build the ``policy`` section for one transaction."""
        pack = self.pack
        if pack is None:
            return {
                "agent": self.name,
                "pack": {"name": "unavailable", "version": "0"},
                "decision": "held",
                "hold_reasons": [PACK_UNAVAILABLE],
                "error": self._pack_error,
                "priority": "deferred",
                "sla_hours": 0,
                "tags": [],
                "dual_approval_required": True,
                "matched_rules": [],
                "decided_by": {},
            }

        try:
            facts = build_facts(transaction)
        except (MoneyError, KeyError, ValueError) as exc:
            # Fail closed (IN-3): if the facts cannot be built, no rule can be trusted.
            return {
                "agent": self.name,
                "pack": {"name": pack.name, "version": pack.version},
                "decision": "held",
                "hold_reasons": ["policy_facts_unavailable"],
                "error": str(exc),
                "priority": "deferred",
                "sla_hours": 0,
                "tags": [],
                "dual_approval_required": True,
                "matched_rules": [],
                "decided_by": {},
            }

        applied = apply_pack(pack, facts)
        outcome = applied["outcome"]
        section = {
            "agent": self.name,
            "pack": applied["pack"],
            "decision": "held" if outcome["hold"] else "approved",
            "hold_reasons": list(outcome["hold_reasons"]),
            "priority": outcome["priority"],
            "sla_hours": outcome["sla_hours"],
            "tags": list(outcome["tags"]),
            "dual_approval_required": bool(outcome["dual_approval_required"]),
            "matched_rules": applied["matched_rules"],
            "decided_by": applied["decided_by"],
            "rules_evaluated": applied["evaluated"],
        }
        for override in ("fee_rate", "fee_floor", "fee_cap", "settlement_lag"):
            if outcome[override] is not None:
                section[override] = outcome[override]
        return section

    def process_message(self, message: dict[str, Any]) -> dict[str, Any]:
        data = self.next_data(message)
        policy = self.apply(data)
        data["policy"] = policy

        if policy["decision"] == "held":
            data["status"] = "held"
            data["hold_reason"] = "; ".join(policy["hold_reasons"])
            return self.finalize(message, data)

        data["status"] = "policy_cleared"
        return self.forward(message, data, NEXT_AGENT)
