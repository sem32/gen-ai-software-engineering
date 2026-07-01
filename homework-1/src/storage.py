"""In-memory storage for transactions.

A single process-wide store backed by a dict keyed on transaction id, insertion
order preserved. No database is used, per the assignment requirements.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .models import Transaction


class TransactionStore:
    def __init__(self) -> None:
        self._items: Dict[str, Transaction] = {}

    def add(self, transaction: Transaction) -> Transaction:
        self._items[transaction.id] = transaction
        return transaction

    def get(self, transaction_id: str) -> Optional[Transaction]:
        return self._items.get(transaction_id)

    def list(self) -> List[Transaction]:
        return list(self._items.values())

    def clear(self) -> None:
        self._items.clear()


# Process-wide singleton used by the app. Tests reset it via ``clear()``.
store = TransactionStore()
