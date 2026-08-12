"""Agent 4 of the runtime pipeline — settlement (spec task T-4).

Consumes compliance-cleared transactions, computes the fee and net amount with ``Decimal``
arithmetic only, derives a business-day value date, and writes the terminal ``settled`` result.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - only when run as a script (PEP 366)
    import sys as _sys

    _sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "agents"

from .base import BaseAgent
from .protocol import MoneyError, parse_amount, parse_timestamp, quantize_money, utc_now_iso

#: 25 basis points, as an exact decimal — never ``0.0025`` the float (guardrail IN-1).
FEE_RATE = Decimal("0.0025")
FEE_FLOOR = Decimal("0.50")
FEE_CAP = Decimal("25.00")

#: Settlement lag in business days per transaction type.
SETTLEMENT_LAG_DAYS: dict[str, int] = {
    "wire_transfer": 2,
    "transfer": 1,
    "payment": 1,
    "refund": 1,
    "direct_debit": 1,
    "deposit": 1,
    "withdrawal": 1,
}
DEFAULT_LAG_DAYS = 2


def _override(raw: Any, label: str) -> Decimal:
    """Parse a policy-supplied monetary override (spec task T-12, edge case EC-20).

    A negative or unparseable override is a :class:`MoneyError` — it never falls back silently to
    the default, because a fee quietly reverting to another figure is unexplainable in an audit.
    """
    value = parse_amount(raw)
    if value < 0:
        raise MoneyError(f"policy override {label} must not be negative, got {raw!r}")
    return value


def calculate_fee(
    amount: Decimal,
    currency: str,
    *,
    rate: Any = None,
    floor: Any = None,
    cap: Any = None,
) -> Decimal:
    """0.25 % of the amount, floored at 0.50 and capped at 25.00 in the transaction currency.

    A rule pack may override the rate, the floor or the cap (spec §3.8). Omitting all three
    reproduces the default behaviour exactly, which is why every pre-CR-01 test still passes.
    """
    effective_rate = FEE_RATE if rate is None else _override(rate, "fee_rate")
    effective_floor = FEE_FLOOR if floor is None else _override(floor, "fee_floor")
    effective_cap = FEE_CAP if cap is None else _override(cap, "fee_cap")

    raw_fee = quantize_money(amount * effective_rate, currency)
    return min(
        max(raw_fee, quantize_money(effective_floor, currency)),
        quantize_money(effective_cap, currency),
    )


def next_business_day(start: date, days: int) -> date:
    """Advance ``start`` by ``days`` business days, skipping Saturdays and Sundays."""
    if days < 0:
        raise ValueError("days must not be negative")
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            remaining -= 1
    return current


def settle_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    """Compute the settlement figures. Pure: the value date comes from the transaction timestamp.

    Honours the optional ``fee_rate`` / ``fee_floor`` / ``fee_cap`` / ``settlement_lag`` overrides
    from the ``policy`` section (spec task T-12). With no policy section, or a policy section that
    sets no override, the result is byte-identical to the pre-CR-01 behaviour.
    """
    policy = transaction.get("policy") or {}
    currency = str(transaction["currency"])
    amount = quantize_money(parse_amount(transaction["amount"]), currency)
    fee = calculate_fee(
        amount,
        currency,
        rate=policy.get("fee_rate"),
        floor=policy.get("fee_floor"),
        cap=policy.get("fee_cap"),
    )
    net_amount = amount - fee

    # Invariant: the ledger must balance exactly after quantisation.
    if fee + net_amount != amount:  # pragma: no cover - defensive, unreachable with quantised inputs
        raise ArithmeticError("fee + net_amount != amount")

    transaction_type = str(transaction.get("transaction_type", ""))
    lag_override = policy.get("settlement_lag")
    if lag_override is None:
        lag = SETTLEMENT_LAG_DAYS.get(transaction_type, DEFAULT_LAG_DAYS)
        lag_source = "default"
    else:
        lag = int(lag_override)
        lag_source = _decided_by(policy, "settlement_lag")
    booked_on = parse_timestamp(transaction["timestamp"]).date()

    return {
        "agent": SettlementProcessor.name,
        "settlement_id": f"STL-{transaction.get('transaction_id', 'UNKNOWN')}",
        "currency": currency,
        "gross_amount": str(amount),
        "fee": str(fee),
        "net_amount": str(net_amount),
        "fee_rate": str(policy.get("fee_rate") or FEE_RATE),
        # Every figure must be explainable: say where the rate and the lag came from.
        "fee_source": "default" if policy.get("fee_rate") is None else _decided_by(policy, "fee_rate"),
        "value_date": next_business_day(booked_on, lag).isoformat(),
        "business_day_lag": lag,
        "lag_source": lag_source,
    }


def _decided_by(policy: dict[str, Any], field: str) -> str:
    """Name the rule that set ``field``, for the settlement audit trail."""
    rule_id = (policy.get("decided_by") or {}).get(field)
    return f"policy:{rule_id}" if rule_id else "policy"


class SettlementProcessor(BaseAgent):
    """Books the cleared transaction and produces the terminal ``settled`` result."""

    name = "settlement_processor"
    inbox = "output"

    def settle(self, transaction: dict[str, Any]) -> dict[str, Any]:
        """Instance-level alias of :func:`settle_transaction`."""
        return settle_transaction(transaction)

    def process_message(self, message: dict[str, Any]) -> dict[str, Any]:
        data = self.next_data(message)
        settlement = settle_transaction(data)
        settlement["settled_at"] = utc_now_iso()  # agent boundary, kept out of the pure function
        data["settlement"] = settlement
        data["status"] = "settled"
        return self.finalize(message, data)
