"""Endpoints for creating, listing, retrieving and exporting transactions."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from .. import services
from ..models import Transaction, TransactionCreate
from ..storage import store

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=Transaction, status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreate) -> Transaction:
    transaction = Transaction.from_create(payload)
    store.add(transaction)
    return transaction


@router.get("", response_model=List[Transaction])
def list_transactions(
    account_id: Optional[str] = Query(None, alias="accountId"),
    type_: Optional[str] = Query(None, alias="type"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
) -> List[Transaction]:
    try:
        return services.filter_transactions(
            store.list(),
            account_id=account_id,
            type_=type_,
            date_from=date_from,
            date_to=date_to,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date filter; use ISO format (YYYY-MM-DD).",
        )


# Declared before the ``/{transaction_id}`` route so "export" is not captured
# as an id path parameter.
@router.get("/export")
def export_transactions(
    format: str = Query("csv"),
    account_id: Optional[str] = Query(None, alias="accountId"),
    type_: Optional[str] = Query(None, alias="type"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
) -> Response:
    if format.lower() != "csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported export format; only 'csv' is supported.",
        )
    try:
        transactions = services.filter_transactions(
            store.list(),
            account_id=account_id,
            type_=type_,
            date_from=date_from,
            date_to=date_to,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date filter; use ISO format (YYYY-MM-DD).",
        )
    csv_text = services.transactions_to_csv(transactions)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )


@router.get("/{transaction_id}", response_model=Transaction)
def get_transaction(transaction_id: str) -> Transaction:
    transaction = store.get(transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{transaction_id}' not found.",
        )
    return transaction
