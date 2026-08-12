"""Schema validation at the HTTP boundary (CR-01.2, spec §3.9).

This is **not** a second copy of the pipeline's business rules. The split is deliberate and it is the
whole reason this module is small:

* **Here (400 ``validation_failed``)** — is this a well-formed *transaction submission*? Right JSON
  types, no unknown fields, required fields present, ``amount`` sent as a string. Getting this wrong
  is a programming error in the client, so it is worth a precise field-level answer before any agent
  runs.
* **The pipeline (422 ``transaction_rejected``)** — is this transaction *acceptable business*?
  ISO 4217 currency, positive amount, account format, matching source and destination. That authority
  stays with :mod:`agents.transaction_validator`, which is also the only path a file-dropped
  transaction takes.

The overlap is limited to field presence, kept on purpose as defence in depth: the pipeline still
emits ``missing_field:*`` for transactions that arrive as files rather than over HTTP.
"""

from __future__ import annotations

from typing import Any

from agents.transaction_validator import REQUIRED_FIELDS

from .errors import ApiProblem, FieldError

#: Optional top-level fields a submission may carry beyond the required ones.
OPTIONAL_FIELDS = ("description", "metadata")
ALLOWED_FIELDS = frozenset(REQUIRED_FIELDS) | frozenset(OPTIONAL_FIELDS)

#: Fields that must arrive as JSON strings. ``amount`` is here on purpose: money crosses the wire as
#: a string so it can become an exact ``Decimal`` (guardrail IN-1). A JSON number would already have
#: been through a float.
STRING_FIELDS = (
    "transaction_id",
    "timestamp",
    "source_account",
    "destination_account",
    "amount",
    "currency",
    "transaction_type",
    "description",
)

MAX_STRING_LENGTH = 256
MAX_METADATA_KEYS = 20


def validate_submission(payload: Any) -> list[FieldError]:
    """Return every schema problem with ``payload``. An empty list means the shape is acceptable."""
    if not isinstance(payload, dict):
        return [
            FieldError(
                "$", "wrong_type", f"a transaction must be a JSON object, got {_kind(payload)}"
            )
        ]

    errors: list[FieldError] = []

    for name in sorted(set(payload) - ALLOWED_FIELDS):
        errors.append(
            FieldError(
                name,
                "unknown_field",
                f"unknown field; allowed: {', '.join(sorted(ALLOWED_FIELDS))}",
            )
        )

    for name in REQUIRED_FIELDS:
        if name not in payload:
            errors.append(FieldError(name, "missing_field", "required field is absent"))

    for name in STRING_FIELDS:
        if name not in payload:
            continue
        value = payload[name]
        if not isinstance(value, str):
            errors.append(
                FieldError(
                    name,
                    "wrong_type",
                    f"expected a string, got {_kind(value)}"
                    + (
                        " — send money as a decimal string so it stays exact"
                        if name == "amount"
                        else ""
                    ),
                )
            )
        elif not value.strip():
            errors.append(FieldError(name, "empty_string", "must not be blank"))
        elif len(value) > MAX_STRING_LENGTH:
            errors.append(
                FieldError(name, "too_long", f"must be at most {MAX_STRING_LENGTH} characters")
            )

    if "metadata" in payload:
        errors.extend(_validate_metadata(payload["metadata"]))

    return errors


def _validate_metadata(metadata: Any) -> list[FieldError]:
    if not isinstance(metadata, dict):
        return [FieldError("metadata", "wrong_type", f"expected an object, got {_kind(metadata)}")]
    if len(metadata) > MAX_METADATA_KEYS:
        return [
            FieldError("metadata", "too_many_keys", f"at most {MAX_METADATA_KEYS} keys are allowed")
        ]
    errors: list[FieldError] = []
    for key, value in sorted(metadata.items()):
        if not isinstance(value, (str, int, bool)) or isinstance(value, float):
            errors.append(
                FieldError(
                    f"metadata.{key}",
                    "wrong_type",
                    f"expected a string, integer or boolean, got {_kind(value)}",
                )
            )
    return errors


def ensure_valid_submission(payload: Any) -> dict[str, Any]:
    """Validate and return the payload, raising :class:`ApiProblem` on the first failing shape."""
    errors = validate_submission(payload)
    if errors:
        raise ApiProblem(
            "validation_failed",
            f"{len(errors)} field problem(s) in the submission",
            errors=[error.as_dict() for error in errors],
        )
    return payload


def _kind(value: Any) -> str:
    """Name a JSON type the way a client would recognise it."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__  # pragma: no cover - unreachable for parsed JSON
