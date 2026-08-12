"""Shared message protocol, money helpers, PII masking and audit logging.

This module is the foundation of the pipeline (spec task T-0). It deliberately depends on the
standard library only — the agents must stay runnable on a bare Python install.

Guardrails implemented here:
  IN-1  money is ``decimal.Decimal`` parsed from ``str``, quantised ROUND_HALF_UP
  IN-2  account identifiers are masked to ``****NNNN`` before they leave the process
  IN-6  ids and timestamps are minted here, so the decision functions stay pure
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

# --------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------


class ProtocolError(ValueError):
    """A message does not satisfy the wire contract, or a payload leaks unmasked PII."""


class MoneyError(ValueError):
    """A monetary value could not be parsed or is not representable as an exact decimal."""


# --------------------------------------------------------------------------------------
# Protocol constants
# --------------------------------------------------------------------------------------

#: Sentinel ``target_agent`` marking a terminal outcome — the message goes to ``shared/results``.
TERMINAL_TARGET = "pipeline_results"

MESSAGE_FIELDS = (
    "message_id",
    "timestamp",
    "source_agent",
    "target_agent",
    "message_type",
    "data",
)

#: Subdirectories of the shared workspace (spec §3.6).
SHARED_SUBDIRS = (
    "input",
    "processing",
    "output",
    "results",
    "reports",
    "audit",
    "quarantine",
)

#: Terminal statuses form a closed set (guardrail IN-5).
TERMINAL_STATUSES = ("rejected", "held", "settled")

# --------------------------------------------------------------------------------------
# Currency reference data
# --------------------------------------------------------------------------------------

#: ISO 4217 alphabetic code -> number of minor units.
ISO_4217_MINOR_UNITS: dict[str, int] = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "CHF": 2,
    "CAD": 2,
    "AUD": 2,
    "SEK": 2,
    "NOK": 2,
    "DKK": 2,
    "PLN": 2,
    "CZK": 2,
    "JPY": 0,
}

#: Illustrative static FX table — demonstration data, NOT a market feed.
#: Used only for threshold comparisons (spec §3.1); never for a settled figure.
USD_RATES: dict[str, str] = {
    "USD": "1.00",
    "EUR": "1.09",
    "GBP": "1.27",
    "CHF": "1.13",
    "CAD": "0.74",
    "AUD": "0.66",
    "SEK": "0.096",
    "NOK": "0.094",
    "DKK": "0.146",
    "PLN": "0.25",
    "CZK": "0.043",
    "JPY": "0.0067",
}

#: Home region of each currency, used by the cross-border fraud rule. Illustrative fixture.
CURRENCY_REGIONS: dict[str, frozenset[str]] = {
    "USD": frozenset({"US"}),
    "GBP": frozenset({"GB"}),
    "JPY": frozenset({"JP"}),
    "CHF": frozenset({"CH", "LI"}),
    "CAD": frozenset({"CA"}),
    "AUD": frozenset({"AU"}),
    "SEK": frozenset({"SE"}),
    "NOK": frozenset({"NO"}),
    "DKK": frozenset({"DK"}),
    "PLN": frozenset({"PL"}),
    "CZK": frozenset({"CZ"}),
    "EUR": frozenset(
        {
            "AT", "BE", "CY", "DE", "EE", "ES", "FI", "FR", "GR", "HR",
            "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PT", "SI", "SK",
        }
    ),
}

ACCOUNT_PATTERN = re.compile(r"^ACC-\d{4}$")
#: Anything account-shaped that survived masking is a PII leak.
_UNMASKED_ACCOUNT = re.compile(r"\bACC-\d{4}\b")

# --------------------------------------------------------------------------------------
# Time and identifiers
# --------------------------------------------------------------------------------------


def utc_now_iso() -> str:
    """Current UTC time as an ISO 8601 string with a ``Z`` suffix (spec §3.3)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_message_id() -> str:
    """A fresh UUID4 string for a message hop."""
    return str(uuid.uuid4())


def parse_timestamp(raw: Any) -> datetime:
    """Parse an ISO 8601 timestamp into an aware UTC ``datetime``.

    Accepts the ``Z`` suffix that ``datetime.fromisoformat`` historically rejected.
    Raises :class:`ProtocolError` for anything unparseable.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ProtocolError(f"timestamp must be a non-empty ISO 8601 string, got {raw!r}")
    candidate = raw.strip()
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:  # pragma: no cover - message varies per Python build
        raise ProtocolError(f"unparseable timestamp {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# --------------------------------------------------------------------------------------
# Money (IN-1)
# --------------------------------------------------------------------------------------


def parse_amount(raw: Any) -> Decimal:
    """Parse a monetary amount from a string into an exact :class:`~decimal.Decimal`.

    ``float`` input is rejected on purpose: ``Decimal(1.1)`` is
    ``Decimal('1.100000000000000088817841970012523233890533447265625')`` and that is a bug,
    not a rounding nuisance (see ``research-notes.md``, query 2).
    """
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, bool) or isinstance(raw, float):
        raise MoneyError(f"monetary amounts must be strings, not {type(raw).__name__}")
    elif isinstance(raw, int):
        value = Decimal(raw)
    elif isinstance(raw, str) and raw.strip():
        try:
            value = Decimal(raw.strip())
        except InvalidOperation as exc:
            raise MoneyError(f"cannot parse amount {raw!r}") from exc
    else:
        raise MoneyError(f"cannot parse amount {raw!r}")

    if not value.is_finite():
        raise MoneyError(f"amount {raw!r} is not finite")
    return value


def minor_units(currency: str) -> int:
    """Number of decimal places for an ISO 4217 code. Raises for an unknown code."""
    try:
        return ISO_4217_MINOR_UNITS[currency]
    except KeyError as exc:
        raise MoneyError(f"unknown currency {currency!r}") from exc


def quantize_money(value: Decimal, currency: str) -> Decimal:
    """Round ``value`` half-up to the currency's minor unit.

    ``ROUND_HALF_UP`` is explicit because Python's decimal default is ``ROUND_HALF_EVEN``
    (banker's rounding), which is not what a settlement ledger expects.
    """
    exponent = Decimal(1).scaleb(-minor_units(currency))
    return value.quantize(exponent, rounding=ROUND_HALF_UP)


def format_money(value: Decimal, currency: str) -> str:
    """Canonical string form of an amount, used on the wire and in reports."""
    return str(quantize_money(value, currency))


def usd_equivalent(amount: Decimal, currency: str) -> Decimal:
    """Approximate USD value, for threshold comparisons only (spec §3.1)."""
    rate = USD_RATES.get(currency)
    if rate is None:
        raise MoneyError(f"no USD rate for currency {currency!r}")
    return (amount * Decimal(rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------------------
# PII masking (IN-2)
# --------------------------------------------------------------------------------------


def mask_account(account: Any) -> str:
    """Reduce an account identifier to ``****`` plus its last four characters."""
    if account is None:
        return "****"
    text = str(account)
    tail = text[-4:] if len(text) >= 4 else text
    return f"****{tail}"


def assert_no_plaintext_pii(payload: Any, *, where: str = "payload") -> None:
    """Raise :class:`ProtocolError` if an unmasked account identifier is present anywhere."""
    if isinstance(payload, str):
        if _UNMASKED_ACCOUNT.search(payload):
            raise ProtocolError(f"unmasked account identifier in {where}: {payload!r}")
    elif isinstance(payload, dict):
        for key, value in payload.items():
            assert_no_plaintext_pii(value, where=f"{where}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_no_plaintext_pii(value, where=f"{where}[{index}]")


# --------------------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------------------


def build_message(
    source_agent: str,
    target_agent: str,
    message_type: str,
    data: dict[str, Any],
    *,
    message_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a protocol message. Every hop mints a fresh ``message_id``."""
    message = {
        "message_id": message_id or new_message_id(),
        "timestamp": timestamp or utc_now_iso(),
        "source_agent": source_agent,
        "target_agent": target_agent,
        "message_type": message_type,
        "data": data,
    }
    validate_message(message)
    return message


def validate_message(message: Any) -> None:
    """Validate a message against the wire contract. Never repairs — only reports."""
    if not isinstance(message, dict):
        raise ProtocolError(f"message must be an object, got {type(message).__name__}")
    for field in MESSAGE_FIELDS:
        if field not in message:
            raise ProtocolError(f"message is missing required field {field!r}")
    for field in ("message_id", "timestamp", "source_agent", "target_agent", "message_type"):
        value = message[field]
        if not isinstance(value, str) or not value.strip():
            raise ProtocolError(f"message field {field!r} must be a non-empty string")
    if not isinstance(message["data"], dict):
        raise ProtocolError("message field 'data' must be an object")
    parse_timestamp(message["timestamp"])


def transaction_id_of(message: dict[str, Any]) -> str:
    """Best-effort transaction id for logging and file naming."""
    data = message.get("data") or {}
    return str(data.get("transaction_id") or "UNKNOWN")


# --------------------------------------------------------------------------------------
# Audit trail (MO-4)
# --------------------------------------------------------------------------------------


class AuditLogger:
    """Append-only JSONL audit trail.

    Refuses to write a record that still contains an unmasked account identifier — the guard is
    part of the control, not a lint rule (guardrail IN-2).
    """

    def __init__(self, log_path: Path) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        agent: str,
        transaction_id: str,
        outcome: str,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "timestamp": utc_now_iso(),
            "agent": agent,
            "transaction_id": transaction_id,
            "outcome": outcome,
            "detail": detail,
        }
        assert_no_plaintext_pii(entry, where="audit_entry")
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            handle.flush()
        return entry

    def entries(self) -> list[dict[str, Any]]:
        """Read the trail back. Used by tests and by the reporting agent."""
        if not self.log_path.exists():
            return []
        with self.log_path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


# --------------------------------------------------------------------------------------
# Shared workspace
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Workspace:
    """Handle on the ``shared/`` directory tree and the audit trail."""

    root: Path

    @classmethod
    def create(cls, root: Path | str, *, reset: bool = False) -> "Workspace":
        root_path = Path(root)
        if reset and root_path.exists():
            shutil.rmtree(root_path)
        for name in SHARED_SUBDIRS:
            (root_path / name).mkdir(parents=True, exist_ok=True)
        return cls(root=root_path)

    # -- directories -------------------------------------------------------------------

    def dir(self, name: str) -> Path:
        if name not in SHARED_SUBDIRS:
            raise ProtocolError(f"unknown shared subdirectory {name!r}")
        return self.root / name

    @property
    def input_dir(self) -> Path:
        return self.dir("input")

    @property
    def processing_dir(self) -> Path:
        return self.dir("processing")

    @property
    def output_dir(self) -> Path:
        return self.dir("output")

    @property
    def results_dir(self) -> Path:
        return self.dir("results")

    @property
    def reports_dir(self) -> Path:
        return self.dir("reports")

    @property
    def quarantine_dir(self) -> Path:
        return self.dir("quarantine")

    @property
    def audit_log_path(self) -> Path:
        return self.dir("audit") / "audit-log.jsonl"

    def audit_logger(self) -> AuditLogger:
        return AuditLogger(self.audit_log_path)

    # -- message I/O -------------------------------------------------------------------

    def write_message(
        self, directory: Path, message: dict[str, Any], *, require_masked: bool = False
    ) -> Path:
        """Write a validated message as a single JSON file and return its path.

        ``require_masked`` enforces guardrail IN-2 and is set for terminal results. Messages still
        in flight (``input``/``processing``/``output``) are internal working state and may carry the
        raw account identifiers the validator needs in order to check their format; from the
        validator onwards every payload is masked anyway.
        """
        validate_message(message)
        if require_masked:
            assert_no_plaintext_pii(message, where="message")
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{transaction_id_of(message)}-{message['message_id'][:8]}.json"
        path = directory / filename
        path.write_text(json.dumps(message, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def iter_inbox(
        self, directory: Path, target_agent: str
    ) -> Iterator[tuple[Path, dict[str, Any] | None, str | None]]:
        """Yield ``(path, message, error)`` for every file addressed to ``target_agent``.

        A malformed or misaddressed file yields ``message=None`` and a reason string so the caller
        can quarantine it and keep going (edge case EC-10).
        """
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.json")):
            try:
                message = json.loads(path.read_text(encoding="utf-8"))
                validate_message(message)
            except (json.JSONDecodeError, ProtocolError) as exc:
                yield path, None, str(exc)
                continue
            if message["target_agent"] != target_agent:
                continue
            yield path, message, None

    def claim(self, path: Path) -> Path:
        """Move a message file into ``processing/`` so it can never be picked up twice."""
        destination = self.processing_dir / path.name
        self.processing_dir.mkdir(parents=True, exist_ok=True)
        return Path(shutil.move(str(path), str(destination)))

    def quarantine(self, path: Path, reason: str) -> Path:
        """Move an unusable file aside and drop a ``.reason`` note next to it."""
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        destination = self.quarantine_dir / path.name
        moved = Path(shutil.move(str(path), str(destination)))
        moved.with_suffix(moved.suffix + ".reason").write_text(reason, encoding="utf-8")
        return moved

    def results(self) -> list[dict[str, Any]]:
        """Every terminal result currently on disk, sorted by transaction id."""
        records: list[dict[str, Any]] = []
        for path in sorted(self.results_dir.glob("*.json")):
            records.append(json.loads(path.read_text(encoding="utf-8")))
        records.sort(key=lambda item: str((item.get("data") or {}).get("transaction_id", "")))
        return records
