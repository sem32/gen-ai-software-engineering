"""Single source of truth for gateway errors (CR-01.2, spec §3.9).

Three things live here and nowhere else:

1. **The catalog** — every error the API can return, with its HTTP status and human title. A code that
   is not in :data:`CATALOG` cannot be raised, which is what stops the status codes drifting apart
   across handlers.
2. **The exception** — :class:`ApiProblem`, the only error type handlers raise.
3. **The serialiser** — :func:`problem_document`, which renders **RFC 9457 Problem Details for HTTP
   APIs** (``application/problem+json``) with our ``code`` / ``request_id`` / ``errors`` extension
   members.

Design notes worth keeping in mind while editing:

* ``type`` is a stable URN. RFC 9457 does not require it to be dereferenceable, and inventing an
  http(s) URL we do not serve would be worse than a URN that is honest about being an identifier.
  The human-readable catalog is [`docs/errors.md`](../docs/errors.md).
* A problem document never carries an upstream exception string on a 5xx path (guardrail IN-10) —
  :func:`problem_from_exception` deliberately discards the original message for unexpected faults and
  logs it instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROBLEM_CONTENT_TYPE = "application/problem+json; charset=utf-8"
PROBLEM_TYPE_PREFIX = "urn:hw6:error:"


@dataclass(frozen=True)
class ErrorDefinition:
    """One entry of the catalog."""

    code: str
    status: int
    title: str
    #: Whether a caller can sensibly retry the identical request.
    retryable: bool = False
    #: Whether the failure is the caller's (4xx) — used only for documentation and tests.
    client_fault: bool = True

    @property
    def type_uri(self) -> str:
        return PROBLEM_TYPE_PREFIX + self.code.replace("_", "-")


def _define(*definitions: ErrorDefinition) -> dict[str, ErrorDefinition]:
    catalog: dict[str, ErrorDefinition] = {}
    for definition in definitions:
        if definition.code in catalog:  # pragma: no cover - guards a copy/paste mistake
            raise ValueError(f"duplicate error code {definition.code!r}")
        catalog[definition.code] = definition
    return catalog


#: Every error the gateway may return. Adding a row is a deliberate, reviewable act.
CATALOG: dict[str, ErrorDefinition] = _define(
    # -- malformed request -------------------------------------------------------------
    ErrorDefinition("invalid_json", 400, "Malformed JSON body"),
    ErrorDefinition("invalid_body", 400, "Request body is not acceptable"),
    ErrorDefinition("invalid_query", 400, "Invalid query parameter"),
    ErrorDefinition("validation_failed", 400, "Submission does not match the transaction schema"),
    ErrorDefinition("payload_too_large", 413, "Request body too large"),
    # -- routing -----------------------------------------------------------------------
    ErrorDefinition("not_found", 404, "No such route"),
    ErrorDefinition("transaction_not_found", 404, "Unknown transaction"),
    ErrorDefinition("method_not_allowed", 405, "Method not allowed on this route"),
    # -- business verdicts -------------------------------------------------------------
    # The transaction WAS processed and IS retrievable; the status communicates the verdict.
    ErrorDefinition("transaction_rejected", 422, "Transaction rejected by the pipeline"),
    ErrorDefinition("transaction_held", 409, "Transaction held for manual review"),
    # -- server ------------------------------------------------------------------------
    ErrorDefinition("rule_pack_unavailable", 500, "Rule pack could not be loaded", client_fault=False),
    ErrorDefinition(
        "pipeline_error", 500, "Pipeline produced no terminal outcome", client_fault=False
    ),
    # CR-02: a downstream agent service could not be reached. Retryable by construction — the hop is
    # idempotent on message_id, so replaying it cannot double-process.
    ErrorDefinition(
        "upstream_unavailable",
        503,
        "A downstream agent service is unavailable",
        retryable=True,
        client_fault=False,
    ),
    ErrorDefinition("internal_error", 500, "Internal error", client_fault=False),
)

#: Business verdict -> catalog code. ``settled`` is a success and is absent on purpose.
VERDICT_CODES: dict[str, str] = {
    "rejected": "transaction_rejected",
    "held": "transaction_held",
}


class ApiProblem(Exception):
    """The only exception the gateway handlers raise."""

    def __init__(self, code: str, detail: str, **extensions: Any) -> None:
        try:
            self.definition = CATALOG[code]
        except KeyError as exc:  # pragma: no cover - a typo in a handler, caught by tests
            raise ValueError(f"unknown error code {code!r}; add it to CATALOG first") from exc
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.extensions = {name: value for name, value in extensions.items() if value is not None}

    @property
    def status(self) -> int:
        return self.definition.status

    @property
    def title(self) -> str:
        return self.definition.title

    def document(self, *, instance: str, request_id: str) -> dict[str, Any]:
        return problem_document(
            self.code,
            detail=self.detail,
            instance=instance,
            request_id=request_id,
            **self.extensions,
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ApiProblem({self.code!r}, status={self.status}, detail={self.detail!r})"


def problem_document(
    code: str,
    *,
    detail: str,
    instance: str,
    request_id: str,
    **extensions: Any,
) -> dict[str, Any]:
    """Render an RFC 9457 problem document.

    The five registered members come first (``type``, ``title``, ``status``, ``detail``,
    ``instance``), then our extensions: ``code`` (the stable machine identifier callers should switch
    on), ``request_id`` (correlates with the audit trail) and anything a handler adds — typically
    ``errors`` for field-level validation or ``outcome`` for a business verdict.
    """
    definition = CATALOG[code]
    document: dict[str, Any] = {
        "type": definition.type_uri,
        "title": definition.title,
        "status": definition.status,
        "detail": detail,
        "instance": instance,
        "code": definition.code,
        "request_id": request_id,
    }
    if definition.retryable:
        document["retryable"] = True
    document.update({name: value for name, value in extensions.items() if value is not None})
    return document


def problem_from_exception(exc: BaseException) -> ApiProblem:
    """Map an unexpected exception onto a catalog entry — the one place that mapping lives.

    Anything not explicitly recognised becomes ``internal_error`` **without** its original message:
    an upstream exception string can carry a filesystem path or a value we masked elsewhere
    (guardrail IN-10). The caller logs the original; the client gets a generic detail.
    """
    if isinstance(exc, ApiProblem):
        return exc

    name = type(exc).__name__
    if name == "TransportError":
        return ApiProblem("upstream_unavailable", str(exc))
    if name == "RuleError":
        return ApiProblem("rule_pack_unavailable", str(exc))
    if name == "ProtocolError":
        return ApiProblem("internal_error", "response failed the redaction check")
    if name == "MoneyError":
        return ApiProblem("validation_failed", str(exc))
    if isinstance(exc, RuntimeError):
        return ApiProblem("pipeline_error", str(exc))
    return ApiProblem("internal_error", "internal error")


def verdict_problem(outcome: dict[str, Any], *, path: str) -> ApiProblem | None:
    """Turn a non-settled pipeline outcome into a problem, or ``None`` when it settled.

    The full outcome travels in the ``outcome`` extension and ``Location`` still points at the stored
    result, because the transaction *was* processed — the 4xx communicates the verdict, not a lost
    request (spec §3.9, edge case EC-22).
    """
    status = str(outcome.get("status", "unknown"))
    code = VERDICT_CODES.get(status)
    if code is None:
        return None

    reasons = outcome.get("rejection_reasons") or outcome.get("hold_reasons") or []
    detail = (
        f"transaction {outcome.get('transaction_id')} was {status}"
        + (f": {', '.join(reasons)}" if reasons else "")
    )
    return ApiProblem(
        code,
        detail,
        reasons=list(reasons),
        outcome=outcome,
        transaction_id=outcome.get("transaction_id"),
    )


@dataclass(frozen=True)
class FieldError:
    """One field-level schema failure, for the ``errors`` extension member."""

    field: str
    code: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "code": self.code, "detail": self.detail}
