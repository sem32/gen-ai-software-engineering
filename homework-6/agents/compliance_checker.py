"""Agent 3 of the runtime pipeline — AML / sanctions screening (spec task T-3).

Consumes fraud-scored transactions and decides ``cleared`` or ``held``. The agent fails closed
(guardrail IN-3): a missing country, an unparseable amount or an absent fraud assessment is a hold,
never a clearance.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - only when run as a script (PEP 366)
    import sys as _sys

    _sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "agents"

from .base import BaseAgent
from .fraud_detector import WATCHLIST_ACCOUNTS
from .protocol import MoneyError, mask_account, parse_amount, usd_equivalent

NEXT_AGENT = "settlement_processor"

#: FinCEN-style Currency Transaction Report threshold — a reporting duty, not a block (spec MO-3).
CTR_THRESHOLD_USD = Decimal("10000")

#: Illustrative sanctions list — demonstration data, not a screening feed.
SANCTIONED_COUNTRIES = frozenset({"IR", "KP", "SY", "CU", "BY"})


def _check(code: str, passed: bool, note: str) -> dict[str, Any]:
    return {"code": code, "passed": passed, "note": note}


def screen_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    """Screen a fraud-scored transaction. Pure: no wall clock, no randomness."""
    checks: list[dict[str, Any]] = []
    hold_reasons: list[str] = []

    # -- reporting duty ---------------------------------------------------------------
    currency = str(transaction.get("currency", ""))
    ctr_required = False
    try:
        usd_amount = usd_equivalent(parse_amount(transaction.get("amount")), currency)
        ctr_required = usd_amount >= CTR_THRESHOLD_USD
        checks.append(
            _check(
                "ctr_threshold",
                True,
                f"{usd_amount} USD-equivalent; CTR {'required' if ctr_required else 'not required'}",
            )
        )
    except MoneyError:
        hold_reasons.append("unparseable_amount")
        checks.append(_check("ctr_threshold", False, "amount could not be evaluated"))

    # -- sanctions --------------------------------------------------------------------
    metadata = transaction.get("metadata") or {}
    country = metadata.get("country")
    if not country:
        hold_reasons.append("missing_country")
        checks.append(_check("sanctions", False, "counterparty country absent — failing closed"))
    elif country in SANCTIONED_COUNTRIES:
        hold_reasons.append(f"sanctioned_country:{country}")
        checks.append(_check("sanctions", False, f"{country} is on the sanctions list"))
    else:
        checks.append(_check("sanctions", True, f"{country} is not on the sanctions list"))

    # -- internal watchlist -----------------------------------------------------------
    destination = str(transaction.get("destination_account", ""))
    if not destination.startswith("****"):
        destination = mask_account(destination)
    if destination in WATCHLIST_ACCOUNTS:
        hold_reasons.append("watchlist_destination")
        checks.append(_check("watchlist", False, "destination account is on the watchlist"))
    else:
        checks.append(_check("watchlist", True, "destination account is not on the watchlist"))

    # -- fraud outcome ----------------------------------------------------------------
    fraud = transaction.get("fraud")
    if not isinstance(fraud, dict):
        hold_reasons.append("missing_fraud_assessment")
        checks.append(_check("fraud_review", False, "no fraud assessment present — failing closed"))
    elif fraud.get("review_required") and fraud.get("risk_level") == "high":
        hold_reasons.append("fraud_review_required")
        checks.append(
            _check("fraud_review", False, f"risk score {fraud.get('risk_score')} requires review")
        )
    else:
        checks.append(
            _check("fraud_review", True, f"risk level {fraud.get('risk_level')} clears automatically")
        )

    return {
        "agent": ComplianceChecker.name,
        "decision": "held" if hold_reasons else "cleared",
        "ctr_required": ctr_required,
        "hold_reasons": hold_reasons,
        "checks": checks,
    }


class ComplianceChecker(BaseAgent):
    """Applies sanctions, watchlist, CTR and fraud-review policy."""

    name = "compliance_checker"
    inbox = "output"

    def screen(self, transaction: dict[str, Any]) -> dict[str, Any]:
        """Instance-level alias of :func:`screen_transaction`."""
        return screen_transaction(transaction)

    def process_message(self, message: dict[str, Any]) -> dict[str, Any]:
        data = self.next_data(message)
        outcome = screen_transaction(data)
        data["compliance"] = outcome

        if outcome["decision"] == "held":
            data["status"] = "held"
            data["hold_reason"] = "; ".join(outcome["hold_reasons"])
            return self.finalize(message, data)

        data["status"] = "compliance_cleared"
        return self.forward(message, data, NEXT_AGENT)
