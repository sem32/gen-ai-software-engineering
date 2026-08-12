"""REST API gateway for the multi-agent banking pipeline (CR-01.2, spec task T-13).

Submodules:

* :mod:`gateway.errors` — the error-code catalog and RFC 9457 problem rendering (the whole system's
  single source of truth for error semantics, services included);
* :mod:`gateway.validation` — schema validation at the HTTP boundary;
* :mod:`gateway.services` — each agent as a stateless callable service;
* :mod:`gateway.server` — routing and the HTTP plumbing.
"""

from __future__ import annotations

from .errors import CATALOG, ApiProblem, problem_document, problem_from_exception
from .server import (
    API_VERSION,
    MAX_BATCH,
    MAX_BODY_BYTES,
    GatewayHandler,
    PipelineGateway,
    create_server,
    main,
)
from .validation import validate_submission

__all__ = [
    "API_VERSION",
    "ApiProblem",
    "CATALOG",
    "GatewayHandler",
    "MAX_BATCH",
    "MAX_BODY_BYTES",
    "PipelineGateway",
    "create_server",
    "main",
    "problem_document",
    "problem_from_exception",
    "validate_submission",
]
