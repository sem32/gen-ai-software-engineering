"""Account-scoped endpoints: balance, summary and simple interest."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException, Query, status

from .. import services
from ..storage import store

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/{account_id}/balance")
def get_balance(account_id: str) -> dict:
    balance = services.account_balance(store.list(), account_id)
    return {"accountId": account_id, "balance": float(balance)}


@router.get("/{account_id}/summary")
def get_summary(account_id: str) -> dict:
    return services.account_summary(store.list(), account_id)


@router.get("/{account_id}/interest")
def get_interest(
    account_id: str,
    rate: str = Query(..., description="Annual interest rate, e.g. 0.05"),
    days: int = Query(..., ge=1, description="Number of days"),
) -> dict:
    try:
        rate_dec = Decimal(str(rate))
    except (InvalidOperation, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rate must be a valid number.",
        )
    if rate_dec < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rate must not be negative.",
        )

    balance = services.account_balance(store.list(), account_id)
    interest = services.simple_interest(balance, rate_dec, days)
    return {
        "accountId": account_id,
        "balance": float(balance),
        "rate": float(rate_dec),
        "days": days,
        "interest": float(interest),
    }
