"""Banking Transactions API — FastAPI application entrypoint.

Wires together the transaction and account routers, a per-IP rate limiter, and
a custom validation-error handler that returns the assignment's error shape:

    {"error": "Validation failed", "details": [{"field": ..., "message": ...}]}
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from .rate_limit import RateLimiter, RateLimitMiddleware
from .routers import accounts, transactions

_VALUE_ERROR_PREFIX = "Value error, "


def create_app() -> FastAPI:
    app = FastAPI(
        title="Banking Transactions API",
        version="1.0.0",
        description="A minimal in-memory REST API for banking transactions.",
    )

    limiter = RateLimiter(
        max_requests=int(os.getenv("RATE_LIMIT_MAX", "100")),
        window_seconds=float(os.getenv("RATE_LIMIT_WINDOW", "60")),
    )
    app.state.rate_limiter = limiter
    app.add_middleware(RateLimitMiddleware, limiter=limiter)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        details = []
        for err in exc.errors():
            loc = [p for p in err.get("loc", ()) if p != "body"]
            field = loc[-1] if loc and isinstance(loc[-1], str) else "body"
            message = err.get("msg", "Invalid value")
            if message.startswith(_VALUE_ERROR_PREFIX):
                message = message[len(_VALUE_ERROR_PREFIX):]
            details.append({"field": field, "message": message})
        return JSONResponse(
            status_code=400,
            content={"error": "Validation failed", "details": details},
        )

    @app.get("/", tags=["meta"])
    def root() -> dict:
        return {"service": "Banking Transactions API", "status": "ok"}

    app.include_router(transactions.router)
    app.include_router(accounts.router)
    return app


app = create_app()
