# Filled in by the import sub-agent.
"""Bulk ticket import endpoints (CSV/JSON/XML).

Provides ``POST /tickets/import`` which accepts a multipart file upload in
one of three formats (CSV, JSON, or XML), parses it into ticket records,
validates each record against ``TicketCreate``, stores the valid ones, and
returns a summary of successes and per-record failures.
"""

from typing import Optional

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..models import Ticket, TicketCreate
from ..parsers import ParseError, parse_csv, parse_json, parse_xml
from ..storage import store

router = APIRouter(prefix="/tickets", tags=["import"])

_PARSERS = {
    "csv": parse_csv,
    "json": parse_json,
    "xml": parse_xml,
}


def _detect_format(explicit_format: Optional[str], filename: Optional[str]) -> Optional[str]:
    """Resolve the import format from the ``format`` query param or filename
    extension. Returns ``None`` if it cannot be determined."""
    if explicit_format:
        candidate = explicit_format.strip().lower()
        if candidate in _PARSERS:
            return candidate
        return None

    if filename:
        lowered = filename.strip().lower()
        for ext, fmt in ((".csv", "csv"), (".json", "json"), (".xml", "xml")):
            if lowered.endswith(ext):
                return fmt

    return None


def _format_validation_errors(exc: ValidationError) -> list[str]:
    """Render pydantic errors as ``"field: message"`` strings."""
    formatted = []
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", []) if part != "body"]
        field = loc[-1] if loc else "body"
        message = error.get("msg", "")
        if message.startswith("Value error, "):
            message = message[len("Value error, "):]
        formatted.append(f"{field}: {message}")
    return formatted


@router.post("/import")
async def import_tickets(
    file: UploadFile,
    format: Optional[str] = None,
    auto_classify: bool = False,
) -> JSONResponse:
    """Bulk-import tickets from an uploaded CSV, JSON, or XML file.

    The format is taken from the ``format`` query param if given, otherwise
    inferred from the uploaded filename's extension. Each record is validated
    independently: invalid records are skipped and reported in ``errors``
    while valid ones are stored. Set ``auto_classify=true`` to run the
    classifier on each successfully created ticket.
    """
    fmt = _detect_format(format, file.filename)
    if fmt is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Import failed",
                "message": (
                    "Could not determine file format. Pass ?format=csv|json|xml "
                    "or upload a file with a .csv, .json, or .xml extension."
                ),
            },
        )

    raw_bytes = await file.read()
    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "Import failed", "message": f"File is not valid UTF-8: {exc}"},
        )

    parser = _PARSERS[fmt]
    try:
        records = parser(content)
    except ParseError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "Import failed", "message": str(exc)},
        )

    total = len(records)
    successful = 0
    errors: list[dict] = []
    created_ids: list[str] = []

    for index, record in enumerate(records):
        try:
            ticket_create = TicketCreate(**record)
        except ValidationError as exc:
            errors.append({"index": index, "errors": _format_validation_errors(exc)})
            continue

        ticket = Ticket.from_create(ticket_create)
        if auto_classify:
            from ..classification import classify

            result = classify(ticket.subject, ticket.description)
            ticket.category = result["category"]
            ticket.priority = result["priority"]
            ticket.classification = result

        store.add(ticket)
        successful += 1
        created_ids.append(ticket.id)

    return JSONResponse(
        status_code=200,
        content={
            "total": total,
            "successful": successful,
            "failed": total - successful,
            "errors": errors,
            "created_ids": created_ids,
        },
    )
