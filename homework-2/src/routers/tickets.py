"""CRUD + auto-classification endpoints for support tickets."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from ..classification import classify
from ..models import Ticket, TicketCreate, TicketUpdate
from ..storage import store

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Ticket)
def create_ticket(payload: TicketCreate, auto_classify: bool = False) -> Ticket:
    """Create a ticket. When ``auto_classify`` is true, run the classifier and
    apply its category/priority, storing the full result on the ticket."""
    ticket = Ticket.from_create(payload)
    if auto_classify:
        result = classify(ticket.subject, ticket.description)
        ticket.category = result["category"]
        ticket.priority = result["priority"]
        ticket.classification = result
    store.add(ticket)
    return ticket


@router.get("", response_model=list[Ticket])
def list_tickets(
    category: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    assigned_to: Optional[str] = Query(default=None),
    customer_id: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> list[Ticket]:
    """List tickets, optionally filtered by any combination of fields."""
    tickets = store.list()
    if category is not None:
        tickets = [t for t in tickets if t.category == category]
    if priority is not None:
        tickets = [t for t in tickets if t.priority == priority]
    if status is not None:
        tickets = [t for t in tickets if t.status == status]
    if assigned_to is not None:
        tickets = [t for t in tickets if t.assigned_to == assigned_to]
    if customer_id is not None:
        tickets = [t for t in tickets if t.customer_id == customer_id]
    if tag is not None:
        tickets = [t for t in tickets if tag in t.tags]
    return tickets


@router.get("/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: str) -> Ticket:
    """Return a single ticket by id, or 404 if it does not exist."""
    ticket = store.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.put("/{ticket_id}", response_model=Ticket)
def update_ticket(ticket_id: str, payload: TicketUpdate) -> Ticket:
    """Partially update a ticket. Bumps ``updated_at`` and sets ``resolved_at``
    when the status transitions to resolved/closed and it was not already set."""
    ticket = store.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(ticket, field, value)

    ticket.updated_at = _now()
    if ticket.status in {"resolved", "closed"} and ticket.resolved_at is None:
        ticket.resolved_at = _now()

    store.update(ticket_id, ticket)
    return ticket


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(ticket_id: str) -> None:
    """Delete a ticket by id, or 404 if it does not exist."""
    if not store.delete(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return None


@router.post("/{ticket_id}/auto-classify")
def auto_classify_ticket(ticket_id: str) -> dict:
    """Run the classifier on a stored ticket, apply the resulting category and
    priority, persist the full result, and return it."""
    ticket = store.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    result = classify(ticket.subject, ticket.description)
    ticket.category = result["category"]
    ticket.priority = result["priority"]
    ticket.classification = result
    ticket.updated_at = _now()
    store.update(ticket_id, ticket)
    return result
