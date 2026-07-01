"""Business logic: filtering, balances, summaries, interest, and CSV export.

All monetary aggregation is performed with :class:`decimal.Decimal`. Only
``completed`` transactions affect balances and monetary totals; ``pending`` and
``failed`` transactions are still listed and counted but do not move money.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import List, Optional

from .models import Transaction


def _as_utc(value: datetime) -> datetime:
    """Return a timezone-aware datetime in UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_date_boundary(value: str, *, end_of_day: bool) -> datetime:
    """Parse a ``from``/``to`` query value into a UTC datetime boundary.

    A pure date (``YYYY-MM-DD``) expands to the start of that day for ``from``
    and the end of that day for ``to`` so a single-day range is inclusive.
    """
    parsed = datetime.fromisoformat(value)
    if len(value) == 10 and parsed.time() == time(0, 0):  # date-only input
        boundary = time.max if end_of_day else time.min
        parsed = datetime.combine(parsed.date(), boundary)
    return _as_utc(parsed)


def filter_transactions(
    transactions: List[Transaction],
    *,
    account_id: Optional[str] = None,
    type_: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Transaction]:
    """Apply the (combinable) history filters to a list of transactions."""
    result = transactions

    if account_id is not None:
        result = [
            t for t in result
            if t.fromAccount == account_id or t.toAccount == account_id
        ]

    if type_ is not None:
        type_ = type_.lower()
        result = [t for t in result if t.type == type_]

    if date_from is not None:
        start = parse_date_boundary(date_from, end_of_day=False)
        result = [t for t in result if _as_utc(t.timestamp) >= start]

    if date_to is not None:
        end = parse_date_boundary(date_to, end_of_day=True)
        result = [t for t in result if _as_utc(t.timestamp) <= end]

    return result


def account_balance(transactions: List[Transaction], account_id: str) -> Decimal:
    """Net balance for an account across all completed transactions."""
    balance = Decimal("0")
    for t in transactions:
        if t.status != "completed":
            continue
        if t.toAccount == account_id:
            balance += t.amount
        if t.fromAccount == account_id:
            balance -= t.amount
    return balance


def account_summary(transactions: List[Transaction], account_id: str) -> dict:
    """Aggregate figures for ``GET /accounts/:id/summary``."""
    total_deposits = Decimal("0")
    total_withdrawals = Decimal("0")
    involved: List[Transaction] = []

    for t in transactions:
        touches = t.fromAccount == account_id or t.toAccount == account_id
        if not touches:
            continue
        involved.append(t)
        if t.status != "completed":
            continue
        if t.toAccount == account_id:
            total_deposits += t.amount
        if t.fromAccount == account_id:
            total_withdrawals += t.amount

    most_recent = (
        max(involved, key=lambda t: _as_utc(t.timestamp)).timestamp.isoformat()
        if involved
        else None
    )

    return {
        "accountId": account_id,
        "totalDeposits": float(total_deposits),
        "totalWithdrawals": float(total_withdrawals),
        "transactionCount": len(involved),
        "mostRecentTransactionDate": most_recent,
    }


def simple_interest(balance: Decimal, rate: Decimal, days: int) -> Decimal:
    """Simple interest: balance * rate * days / 365, rounded to 2 decimals."""
    interest = balance * rate * Decimal(days) / Decimal(365)
    return interest.quantize(Decimal("0.01"))


def transactions_to_csv(transactions: List[Transaction]) -> str:
    """Serialize transactions to CSV text."""
    buffer = io.StringIO()
    fieldnames = [
        "id", "fromAccount", "toAccount", "amount",
        "currency", "type", "timestamp", "status",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for t in transactions:
        writer.writerow(
            {
                "id": t.id,
                "fromAccount": t.fromAccount or "",
                "toAccount": t.toAccount or "",
                "amount": f"{t.amount:.2f}",
                "currency": t.currency,
                "type": t.type,
                "timestamp": t.timestamp.isoformat(),
                "status": t.status,
            }
        )
    return buffer.getvalue()
