"""In-memory persistence layer for tickets.

Provides :class:`TicketStore`, a thin wrapper over an insertion-ordered dict
keyed by ticket id. A module-level singleton ``store`` is shared by the routers
so all requests operate on the same data within a process. Suitable for a
training exercise; swap for a real database in production.
"""

from typing import Optional

from .models import Ticket


class TicketStore:
    """Insertion-ordered, in-memory collection of tickets keyed by id."""

    def __init__(self) -> None:
        self._tickets: dict[str, Ticket] = {}

    def add(self, ticket: Ticket) -> Ticket:
        """Store a ticket and return it."""
        self._tickets[ticket.id] = ticket
        return ticket

    def get(self, ticket_id: str) -> Optional[Ticket]:
        """Return the ticket with ``ticket_id`` or ``None`` if absent."""
        return self._tickets.get(ticket_id)

    def list(self) -> list[Ticket]:
        """Return all tickets in insertion order."""
        return list(self._tickets.values())

    def update(self, ticket_id: str, ticket: Ticket) -> Ticket:
        """Replace the ticket stored under ``ticket_id`` and return it."""
        self._tickets[ticket_id] = ticket
        return ticket

    def delete(self, ticket_id: str) -> bool:
        """Delete a ticket; return ``True`` if it existed, ``False`` otherwise."""
        if ticket_id in self._tickets:
            del self._tickets[ticket_id]
            return True
        return False

    def clear(self) -> None:
        """Remove all tickets (primarily for tests)."""
        self._tickets.clear()


store = TicketStore()
