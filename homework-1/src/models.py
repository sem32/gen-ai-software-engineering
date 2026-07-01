"""Pydantic models for the Banking Transactions API.

Monetary amounts are handled as :class:`decimal.Decimal` to avoid the rounding
errors inherent to binary floating point. They are parsed from the raw request
value via ``str()`` so that literals such as ``100.50`` keep exactly two decimal
places instead of picking up float noise.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from .constants import (
    ACCOUNT_PATTERN,
    TRANSACTION_STATUSES,
    TRANSACTION_TYPES,
    VALID_CURRENCIES,
)

import re

_ACCOUNT_RE = re.compile(ACCOUNT_PATTERN)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TransactionCreate(BaseModel):
    """Payload accepted by ``POST /transactions``."""

    fromAccount: Optional[str] = None
    toAccount: Optional[str] = None
    amount: Decimal
    currency: str
    type: str
    status: str = "completed"
    timestamp: Optional[datetime] = None

    @field_validator("amount", mode="before")
    @classmethod
    def _parse_amount(cls, value: object) -> Decimal:
        # bool is a subclass of int; reject it explicitly.
        if isinstance(value, bool) or value is None:
            raise ValueError("Amount must be a positive number")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("Amount must be a valid number")

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Amount must be a positive number")
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("Amount must have at most 2 decimal places")
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, value: str) -> str:
        if value not in VALID_CURRENCIES:
            raise ValueError("Invalid currency code")
        return value

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        if value not in TRANSACTION_TYPES:
            raise ValueError("Invalid transaction type")
        return value

    @field_validator("status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        if value not in TRANSACTION_STATUSES:
            raise ValueError("Invalid status")
        return value

    @field_validator("fromAccount", "toAccount")
    @classmethod
    def _check_account_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not _ACCOUNT_RE.match(value):
            raise ValueError("Account number must match the format ACC-XXXXX")
        return value

    @model_validator(mode="after")
    def _check_account_presence(self) -> "TransactionCreate":
        if self.type == "transfer":
            if not self.fromAccount or not self.toAccount:
                raise ValueError("Transfers require both fromAccount and toAccount")
        elif self.type == "deposit":
            if not self.toAccount:
                raise ValueError("Deposits require toAccount")
        elif self.type == "withdrawal":
            if not self.fromAccount:
                raise ValueError("Withdrawals require fromAccount")
        return self


class Transaction(BaseModel):
    """A stored transaction, returned by the read endpoints."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    fromAccount: Optional[str] = None
    toAccount: Optional[str] = None
    amount: Decimal
    currency: str
    type: str
    timestamp: datetime = Field(default_factory=_now)
    status: str = "completed"

    @field_serializer("amount")
    def _serialize_amount(self, value: Decimal) -> float:
        return float(value)

    @field_serializer("timestamp")
    def _serialize_timestamp(self, value: datetime) -> str:
        return value.isoformat()

    @classmethod
    def from_create(cls, payload: TransactionCreate) -> "Transaction":
        return cls(
            fromAccount=payload.fromAccount,
            toAccount=payload.toAccount,
            amount=payload.amount,
            currency=payload.currency,
            type=payload.type,
            status=payload.status,
            timestamp=payload.timestamp or _now(),
        )
