"""Agent 1 of the runtime pipeline — structural validation (spec task T-1).

Consumes raw transactions from ``shared/input``. Valid ones are forwarded to the fraud detector
with ``status="validated"``; invalid ones are terminal and land in ``shared/results`` with the
complete list of stable rejection codes — a rejected transaction gets exactly one round trip.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - only when run as a script (PEP 366)
    import sys as _sys

    _sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "agents"

from .base import BaseAgent
from .protocol import (
    ACCOUNT_PATTERN,
    ISO_4217_MINOR_UNITS,
    MoneyError,
    ProtocolError,
    Workspace,
    format_money,
    mask_account,
    minor_units,
    parse_amount,
    parse_timestamp,
    utc_now_iso,
)

REQUIRED_FIELDS = (
    "transaction_id",
    "timestamp",
    "source_account",
    "destination_account",
    "amount",
    "currency",
    "transaction_type",
)

KNOWN_TRANSACTION_TYPES = frozenset(
    {"transfer", "wire_transfer", "refund", "payment", "deposit", "withdrawal", "direct_debit"}
)

NEXT_AGENT = "fraud_detector"

DEFAULT_SAMPLE = Path(__file__).resolve().parent.parent / "sample-transactions.json"


# --------------------------------------------------------------------------------------
# Pure decision function (guardrail IN-6)
# --------------------------------------------------------------------------------------


def validate_transaction(transaction: dict[str, Any]) -> list[str]:
    """Return every rejection code that applies. An empty list means the record is valid.

    All failing checks are reported, not just the first one — see spec §5 T-1.
    """
    reasons: list[str] = []

    for field in REQUIRED_FIELDS:
        value = transaction.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            reasons.append(f"missing_field:{field}")

    currency = transaction.get("currency")
    currency_known = isinstance(currency, str) and currency in ISO_4217_MINOR_UNITS
    if currency is not None and not currency_known:
        reasons.append(f"unknown_currency:{currency}")

    if transaction.get("amount") is not None:
        reasons.extend(_check_amount(transaction["amount"], currency, currency_known))

    if transaction.get("timestamp") is not None:
        try:
            parse_timestamp(transaction["timestamp"])
        except ProtocolError:
            reasons.append("invalid_timestamp")

    for field in ("source_account", "destination_account"):
        value = transaction.get(field)
        if value is not None and not ACCOUNT_PATTERN.match(str(value)):
            reasons.append(f"invalid_account_format:{field}")

    source = transaction.get("source_account")
    if source is not None and source == transaction.get("destination_account"):
        reasons.append("same_source_and_destination")

    transaction_type = transaction.get("transaction_type")
    if transaction_type is not None and transaction_type not in KNOWN_TRANSACTION_TYPES:
        reasons.append(f"unknown_transaction_type:{transaction_type}")

    metadata = transaction.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        reasons.append("invalid_metadata")

    return reasons


def _check_amount(raw: Any, currency: Any, currency_known: bool) -> list[str]:
    try:
        amount = parse_amount(raw)
    except MoneyError:
        return ["invalid_amount"]

    reasons: list[str] = []
    if amount <= Decimal("0"):
        reasons.append("non_positive_amount")
    if currency_known and -int(amount.as_tuple().exponent) > minor_units(str(currency)):
        reasons.append("too_many_decimal_places")
    return reasons


def redact_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    """Mask account identifiers and drop the customer-supplied description (guardrail IN-2)."""
    data = dict(transaction)
    for field in ("source_account", "destination_account"):
        if field in data:
            data[field] = mask_account(data[field])
    if "description" in data:
        data["description"] = "[redacted]"
    if isinstance(data.get("metadata"), dict):
        data["metadata"] = dict(data["metadata"])
    return data


# --------------------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------------------


class TransactionValidator(BaseAgent):
    """Checks required fields, amount sanity, ISO 4217 currency and account formatting."""

    name = "transaction_validator"
    inbox = "input"

    def validate(self, transaction: dict[str, Any]) -> list[str]:
        """Instance-level alias of :func:`validate_transaction`."""
        return validate_transaction(transaction)

    def process_message(self, message: dict[str, Any]) -> dict[str, Any]:
        raw = self.next_data(message)
        reasons = validate_transaction(raw)
        data = redact_transaction(raw)
        data["validation"] = {
            "agent": self.name,
            "valid": not reasons,
            "reasons": reasons,
            "checked_at": utc_now_iso(),
        }

        if reasons:
            data["status"] = "rejected"
            data["rejection_reasons"] = reasons
            data["rejection_reason"] = "; ".join(reasons)
            return self.finalize(message, data)

        # Normalise the amount to the currency's minor unit exactly once, here (spec §3.1).
        data["amount"] = format_money(parse_amount(raw["amount"]), raw["currency"])
        data["status"] = "validated"
        return self.forward(message, data, NEXT_AGENT)


# --------------------------------------------------------------------------------------
# CLI — dry-run mode writes nothing under shared/
# --------------------------------------------------------------------------------------


def dry_run(sample_path: Path | str = DEFAULT_SAMPLE) -> dict[str, Any]:
    """Validate every record in ``sample_path`` without touching the shared workspace."""
    transactions = json.loads(Path(sample_path).read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for transaction in transactions:
        reasons = validate_transaction(transaction)
        rows.append(
            {
                "transaction_id": transaction.get("transaction_id", "UNKNOWN"),
                "amount": transaction.get("amount"),
                "currency": transaction.get("currency"),
                "valid": not reasons,
                "reasons": reasons,
            }
        )
    return {
        "total": len(rows),
        "valid": sum(1 for row in rows if row["valid"]),
        "invalid": sum(1 for row in rows if not row["valid"]),
        "rows": rows,
    }


def render_dry_run(report: dict[str, Any]) -> str:
    """Render the dry-run report as a fixed-width table."""
    header = f"{'TRANSACTION':<14}{'AMOUNT':>13} {'CUR':<5} {'RESULT':<9}REASONS"
    lines = ["DRY RUN — no files written under shared/", "", header, "-" * max(len(header), 72)]
    for row in report["rows"]:
        verdict = "VALID" if row["valid"] else "INVALID"
        reasons = ", ".join(row["reasons"]) or "-"
        lines.append(
            f"{row['transaction_id']:<14}{str(row['amount']):>13} "
            f"{str(row['currency']):<5} {verdict:<9}{reasons}"
        )
    lines.append("-" * max(len(header), 72))
    lines.append(f"total={report['total']}  valid={report['valid']}  invalid={report['invalid']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transaction validator agent")
    parser.add_argument("--dry-run", action="store_true", help="validate without writing anything")
    parser.add_argument("--sample", default=str(DEFAULT_SAMPLE), help="path to the sample file")
    parser.add_argument("--shared", default="shared", help="shared workspace root")
    args = parser.parse_args(argv)

    if args.dry_run:
        print(render_dry_run(dry_run(args.sample)))
        return 0

    workspace = Workspace.create(args.shared)
    emitted = TransactionValidator(workspace).run()
    print(f"{TransactionValidator.name}: processed {len(emitted)} message(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point, exercised manually and by the skill
    raise SystemExit(main())
