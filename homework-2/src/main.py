"""Application entry point for the Customer Support Ticket API.

Uses an app-factory pattern (:func:`create_app`) so tests can build isolated
instances, wires up the ticket and import routers, and installs a custom
``RequestValidationError`` handler that returns HTTP 400 with a clean,
field-oriented error payload instead of FastAPI's default 422 shape.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .routers import imports, tickets

_STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    # Disable the default /docs (which loads Swagger UI assets from a CDN) and
    # serve a self-contained version from bundled static files below, so the
    # interactive docs work fully offline.
    app = FastAPI(title="Customer Support Ticket API", docs_url=None, redoc_url=None)

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/docs", include_in_schema=False)
    def custom_swagger_ui() -> object:
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            swagger_js_url="/static/swagger-ui-bundle.js",
            swagger_css_url="/static/swagger-ui.css",
        )

    app.include_router(tickets.router)
    app.include_router(imports.router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return a 400 with per-field validation details."""
        details = []
        for error in exc.errors():
            loc = [part for part in error.get("loc", []) if part != "body"]
            field = loc[-1] if loc else "body"
            message = error.get("msg", "")
            if message.startswith("Value error, "):
                message = message[len("Value error, "):]
            details.append({"field": field, "message": message})
        return JSONResponse(
            status_code=400,
            content={"error": "Validation failed", "details": details},
        )

    @app.get("/")
    def root() -> dict:
        """Simple service health/identity endpoint."""
        return {"service": "Customer Support Ticket API", "status": "ok"}

    return app


app = create_app()
