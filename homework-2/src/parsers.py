"""Pure parsing utilities for multi-format bulk ticket import.

Each ``parse_*`` function takes raw file content (as ``str``) and returns a
list of normalized dicts shaped so they can be passed directly as
``TicketCreate(**record)``. No HTTP or FastAPI concerns live here - that is
handled by ``src.routers.imports``.

On malformed input (invalid JSON, unparseable XML, unreadable CSV), each
function raises :class:`ParseError` with a human-readable message.
"""

import csv
import io
import json
import xml.etree.ElementTree as ET
from typing import Any, Optional


class ParseError(Exception):
    """Raised when uploaded import content cannot be parsed."""


def _clean_str(value: Optional[str]) -> Optional[str]:
    """Return a stripped string, or ``None`` if empty/blank/absent."""
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _build_metadata(source: Optional[str], browser: Optional[str], device_type: Optional[str]) -> Optional[dict]:
    """Build a metadata dict from flat sub-values, omitting empty ones.

    Returns ``None`` entirely if all sub-values are empty, so the model's
    ``metadata=None`` default applies.
    """
    source = _clean_str(source)
    browser = _clean_str(browser)
    device_type = _clean_str(device_type)
    if source is None and browser is None and device_type is None:
        return None
    return {"source": source, "browser": browser, "device_type": device_type}


def _normalize_record(raw: dict) -> dict:
    """Drop empty optional fields from a raw dict so model defaults apply."""
    record: dict[str, Any] = {}
    for key in ("customer_id", "customer_email", "customer_name", "subject", "description"):
        if key in raw and raw[key] is not None:
            record[key] = raw[key]

    for key in ("category", "priority", "status"):
        value = _clean_str(raw.get(key)) if isinstance(raw.get(key), str) else raw.get(key)
        if value:
            record[key] = value

    assigned_to = raw.get("assigned_to")
    assigned_to = _clean_str(assigned_to) if isinstance(assigned_to, str) else assigned_to
    if assigned_to:
        record["assigned_to"] = assigned_to

    tags = raw.get("tags")
    record["tags"] = tags if tags else []

    metadata = raw.get("metadata")
    if metadata:
        record["metadata"] = metadata

    return record


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #

_CSV_COLUMNS = [
    "customer_id",
    "customer_email",
    "customer_name",
    "subject",
    "description",
    "category",
    "priority",
    "status",
    "assigned_to",
    "tags",
    "source",
    "browser",
    "device_type",
]


def parse_csv(content: str) -> list[dict]:
    """Parse CSV content into a list of normalized ticket dicts.

    Expects the header row:
    ``customer_id,customer_email,customer_name,subject,description,category,
    priority,status,assigned_to,tags,source,browser,device_type``
    where ``tags`` is ``;``-separated.
    """
    try:
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
    except csv.Error as exc:
        raise ParseError(f"Unable to read CSV content: {exc}") from exc

    if reader.fieldnames is None:
        raise ParseError("CSV content has no header row")

    missing = [col for col in _CSV_COLUMNS if col not in reader.fieldnames]
    if missing:
        raise ParseError(f"CSV is missing required columns: {', '.join(missing)}")

    records = []
    for row in rows:
        tags_raw = row.get("tags") or ""
        tags = [t.strip() for t in tags_raw.split(";") if t.strip()]

        raw = {
            "customer_id": _clean_str(row.get("customer_id")),
            "customer_email": _clean_str(row.get("customer_email")),
            "customer_name": _clean_str(row.get("customer_name")),
            "subject": row.get("subject"),
            "description": row.get("description"),
            "category": row.get("category"),
            "priority": row.get("priority"),
            "status": row.get("status"),
            "assigned_to": row.get("assigned_to"),
            "tags": tags,
            "metadata": _build_metadata(row.get("source"), row.get("browser"), row.get("device_type")),
        }
        records.append(_normalize_record(raw))

    return records


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #


def parse_json(content: str) -> list[dict]:
    """Parse a JSON array of ticket objects into a list of normalized dicts."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ParseError("JSON content must be an array of ticket objects")

    records = []
    for item in data:
        if not isinstance(item, dict):
            raise ParseError("Each JSON ticket entry must be an object")

        metadata_raw = item.get("metadata") or {}
        if not isinstance(metadata_raw, dict):
            raise ParseError("Ticket 'metadata' must be an object")

        raw = {
            "customer_id": item.get("customer_id"),
            "customer_email": item.get("customer_email"),
            "customer_name": item.get("customer_name"),
            "subject": item.get("subject"),
            "description": item.get("description"),
            "category": item.get("category"),
            "priority": item.get("priority"),
            "status": item.get("status"),
            "assigned_to": item.get("assigned_to"),
            "tags": item.get("tags") or [],
            "metadata": _build_metadata(
                metadata_raw.get("source"),
                metadata_raw.get("browser"),
                metadata_raw.get("device_type"),
            ),
        }
        records.append(_normalize_record(raw))

    return records


# --------------------------------------------------------------------------- #
# XML
# --------------------------------------------------------------------------- #


def _text(element: Optional[ET.Element]) -> Optional[str]:
    """Return the text content of an element, or ``None`` if absent/empty."""
    if element is None or element.text is None:
        return None
    return element.text


def parse_xml(content: str) -> list[dict]:
    """Parse ``<tickets><ticket>...</ticket></tickets>`` XML into dicts."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ParseError(f"Invalid XML: {exc}") from exc

    records = []
    for ticket_el in root.findall("ticket"):
        tags = [
            tag_el.text.strip()
            for tag_el in ticket_el.findall("./tags/tag")
            if tag_el.text and tag_el.text.strip()
        ]

        metadata_el = ticket_el.find("metadata")
        source = browser = device_type = None
        if metadata_el is not None:
            source = _text(metadata_el.find("source"))
            browser = _text(metadata_el.find("browser"))
            device_type = _text(metadata_el.find("device_type"))

        raw = {
            "customer_id": _text(ticket_el.find("customer_id")),
            "customer_email": _text(ticket_el.find("customer_email")),
            "customer_name": _text(ticket_el.find("customer_name")),
            "subject": _text(ticket_el.find("subject")),
            "description": _text(ticket_el.find("description")),
            "category": _text(ticket_el.find("category")),
            "priority": _text(ticket_el.find("priority")),
            "status": _text(ticket_el.find("status")),
            "assigned_to": _text(ticket_el.find("assigned_to")),
            "tags": tags,
            "metadata": _build_metadata(source, browser, device_type),
        }
        records.append(_normalize_record(raw))

    return records
