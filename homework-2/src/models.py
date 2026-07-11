"""Pydantic v2 models for the Customer Support Ticket API.

Defines the request/response shapes used across the service:

* :class:`Metadata` - optional contextual info about a ticket's origin.
* :class:`TicketCreate` - payload accepted when creating a ticket.
* :class:`TicketUpdate` - partial payload accepted for updates (all optional).
* :class:`Ticket` - the stored/served representation, including server-managed
  timestamps and an optional auto-classification result.

Field-level validators raise ``ValueError`` with per-field messages so the
custom ``RequestValidationError`` handler in ``main.py`` can surface clean,
consumer-friendly error details.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator

from .constants import CATEGORIES, DEVICE_TYPES, PRIORITIES, SOURCES, STATUSES


def _now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Metadata(BaseModel):
    """Optional contextual metadata describing where a ticket came from."""

    source: Optional[str] = None
    browser: Optional[str] = None
    device_type: Optional[str] = None

    @field_validator("source")
    @classmethod
    def _validate_source(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in SOURCES:
            raise ValueError("Invalid source")
        return value

    @field_validator("device_type")
    @classmethod
    def _validate_device_type(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in DEVICE_TYPES:
            raise ValueError("Invalid device_type")
        return value


class TicketCreate(BaseModel):
    """Payload accepted when creating a new support ticket."""

    customer_id: str
    customer_email: EmailStr
    customer_name: str
    subject: str
    description: str
    category: str = "other"
    priority: str = "medium"
    status: str = "new"
    assigned_to: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: Optional[Metadata] = None

    @field_validator("customer_id")
    @classmethod
    def _validate_customer_id(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("customer_id must not be empty")
        return value

    @field_validator("customer_name")
    @classmethod
    def _validate_customer_name(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("customer_name must not be empty")
        return value

    @field_validator("subject")
    @classmethod
    def _validate_subject(cls, value: str) -> str:
        if not (1 <= len(value) <= 200):
            raise ValueError("Subject must be 1-200 characters")
        return value

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str) -> str:
        if not (10 <= len(value) <= 2000):
            raise ValueError("Description must be 10-2000 characters")
        return value

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError("Invalid category")
        return value

    @field_validator("priority")
    @classmethod
    def _validate_priority(cls, value: str) -> str:
        if value not in PRIORITIES:
            raise ValueError("Invalid priority")
        return value

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in STATUSES:
            raise ValueError("Invalid status")
        return value


class TicketUpdate(BaseModel):
    """Partial update payload; every field is optional for PUT semantics."""

    customer_id: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_name: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    tags: Optional[list[str]] = None
    metadata: Optional[Metadata] = None

    @field_validator("customer_id")
    @classmethod
    def _validate_customer_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("customer_id must not be empty")
        return value

    @field_validator("customer_name")
    @classmethod
    def _validate_customer_name(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("customer_name must not be empty")
        return value

    @field_validator("subject")
    @classmethod
    def _validate_subject(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not (1 <= len(value) <= 200):
            raise ValueError("Subject must be 1-200 characters")
        return value

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not (10 <= len(value) <= 2000):
            raise ValueError("Description must be 10-2000 characters")
        return value

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in CATEGORIES:
            raise ValueError("Invalid category")
        return value

    @field_validator("priority")
    @classmethod
    def _validate_priority(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PRIORITIES:
            raise ValueError("Invalid priority")
        return value

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in STATUSES:
            raise ValueError("Invalid status")
        return value


class Ticket(BaseModel):
    """The stored/served representation of a support ticket."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    customer_id: str
    customer_email: EmailStr
    customer_name: str
    subject: str
    description: str
    category: str = "other"
    priority: str = "medium"
    status: str = "new"
    assigned_to: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: Optional[Metadata] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    resolved_at: Optional[datetime] = None
    classification: Optional[dict] = None

    @field_serializer("created_at", "updated_at")
    def _serialize_required_datetime(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer("resolved_at")
    def _serialize_optional_datetime(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value is not None else None

    @classmethod
    def from_create(cls, payload: "TicketCreate") -> "Ticket":
        """Build a stored :class:`Ticket` from a validated create payload.

        Stamps ``created_at`` and ``updated_at`` to the current UTC time.
        """
        now = _now()
        return cls(
            customer_id=payload.customer_id,
            customer_email=payload.customer_email,
            customer_name=payload.customer_name,
            subject=payload.subject,
            description=payload.description,
            category=payload.category,
            priority=payload.priority,
            status=payload.status,
            assigned_to=payload.assigned_to,
            tags=list(payload.tags),
            metadata=payload.metadata,
            created_at=now,
            updated_at=now,
        )
