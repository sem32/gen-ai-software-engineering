"""REST API gateway in front of the file-based pipeline (spec task T-13, objective MO-8).

Standard library only — ``http.server.ThreadingHTTPServer``. That is a deliberate constraint, not a
shortcut: the project's "runs on a bare Python install" property is worth more here than the
ergonomics of a framework, and it keeps ``demo.sh`` dependency-free.

The gateway owns **no decision logic** (guardrail IN-8). It seeds a message, drains the same agents
in the same order as the CLI, and then reads the same masked artefacts. Every response is built from
what the pipeline already wrote, so the HTTP surface cannot leak an identifier the file surface would
not (guardrail IN-10).

Error handling is centralised: :mod:`gateway.errors` owns the code catalog and the RFC 9457 rendering,
:mod:`gateway.validation` owns the schema check at the boundary, and every failure — expected or not —
leaves this module through exactly one funnel in :meth:`GatewayHandler._handle`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    # append, never insert: the sibling `mcp/` directory must not shadow the installed `mcp` package
    sys.path.append(str(PROJECT_ROOT))

from agents import results_store  # noqa: E402
from agents.policy_engine import available_packs, resolve_pack  # noqa: E402
from agents.protocol import Workspace, assert_no_plaintext_pii  # noqa: E402
from agents.reporting_agent import ReportingAgent, render_markdown  # noqa: E402
from integrator import DEFAULT_SAMPLE, run_pipeline, submit_transaction_traced  # noqa: E402

from .errors import (  # noqa: E402
    PROBLEM_CONTENT_TYPE,
    ApiProblem,
    problem_from_exception,
    verdict_problem,
)
from .services import AGENT_SERVICES, chain, describe_agents, invoke  # noqa: E402
from .validation import ensure_valid_submission  # noqa: E402

API_VERSION = "2.0"
SERVICE_NAME = "pipeline-gateway"

#: Bodies above this are refused rather than buffered (edge case EC-23).
MAX_BODY_BYTES = 1024 * 1024
#: An oversized body is still drained up to here so the client can read the 413 it earned.
DRAIN_CEILING_BYTES = 8 * 1024 * 1024
#: A batch larger than this is refused — a demo surface should not be a load generator.
MAX_BATCH = 200
AUDIT_DEFAULT_LIMIT = 50
AUDIT_MAX_LIMIT = 500

JSON_CONTENT_TYPE = "application/json; charset=utf-8"
MARKDOWN_CONTENT_TYPE = "text/markdown; charset=utf-8"


@dataclass
class Response:
    """What a handler returns on the success path. Failures raise :class:`ApiProblem` instead."""

    status: int
    payload: Any = None
    headers: dict[str, str] | None = None
    content_type: str = JSON_CONTENT_TYPE
    text: str | None = None


@dataclass(frozen=True)
class Route:
    method: str
    pattern: re.Pattern[str]
    handler: str
    summary: str


# --------------------------------------------------------------------------------------
# Gateway
# --------------------------------------------------------------------------------------


class PipelineGateway:
    """Routing plus handlers. Holds the workspace and serialises pipeline drains."""

    #: The whole HTTP surface, as data, so a test can enumerate it (spec §3.9).
    ROUTES: tuple[Route, ...] = (
        Route("GET", re.compile(r"^/$"), "handle_presentation", "the interactive presentation"),
        Route(
            "GET",
            re.compile(r"^/presentation(?:\.html)?$"),
            "handle_presentation",
            "the interactive presentation",
        ),
        Route("GET", re.compile(r"^/health$"), "handle_health", "liveness and configuration"),
        Route("GET", re.compile(r"^/rules$"), "handle_rules", "the active rule pack"),
        Route("GET", re.compile(r"^/errors$"), "handle_errors", "the error code catalog"),
        Route("POST", re.compile(r"^/transactions$"), "handle_submit", "submit one transaction"),
        Route(
            "POST",
            re.compile(r"^/transactions/batch$"),
            "handle_submit_batch",
            "submit an array of transactions",
        ),
        Route("GET", re.compile(r"^/transactions$"), "handle_list", "list processed transactions"),
        Route(
            "GET",
            re.compile(r"^/transactions/(?P<transaction_id>[A-Za-z0-9_.:-]{1,64})$"),
            "handle_get",
            "one terminal outcome",
        ),
        Route("GET", re.compile(r"^/agents$"), "handle_agents", "the agent catalog"),
        Route(
            "POST",
            re.compile(r"^/agents/(?P<agent_name>[a-z_]{1,64})/process$"),
            "handle_agent_process",
            "run one agent over one message (stateless)",
        ),
        Route("POST", re.compile(r"^/pipeline/run$"), "handle_run_sample", "run the bundled sample"),
        Route(
            "POST",
            re.compile(r"^/pipeline/chain$"),
            "handle_chain",
            "drive one payload through every agent, hop by hop, writing nothing",
        ),
        Route("GET", re.compile(r"^/summary$"), "handle_summary", "run summary as JSON"),
        Route(
            "GET",
            re.compile(r"^/summary\.md$"),
            "handle_summary_markdown",
            "run summary as Markdown",
        ),
        Route("GET", re.compile(r"^/audit$"), "handle_audit", "tail of the audit trail"),
    )

    #: ``inprocess`` drains the agents in this process (the batch path, and what the test suite uses);
    #: ``rest`` hands the message to the first agent *service* and lets the chain choreograph itself
    #: over HTTP (CR-02). Both drive the same decision functions.
    TRANSPORTS = ("inprocess", "rest")

    def __init__(
        self,
        shared_root: Path | str,
        sample_path: Path | str = DEFAULT_SAMPLE,
        rules: str | None = None,
        transport: str = "inprocess",
        topology: Any = None,
    ) -> None:
        if transport not in self.TRANSPORTS:
            raise ValueError(f"transport must be one of {self.TRANSPORTS}, got {transport!r}")
        self.workspace = Workspace.create(shared_root)
        self.sample_path = Path(sample_path)
        self.rules = rules
        self.transport = transport
        self._topology = topology
        self.started_at = time.monotonic()
        self._lock = threading.Lock()

    @property
    def topology(self):
        """Resolved lazily so an ``inprocess`` gateway never needs a topology at all."""
        if self._topology is None:
            from services.topology import load_topology

            self._topology = load_topology()
        return self._topology

    # -- helpers -----------------------------------------------------------------------

    @property
    def shared_root(self) -> Path:
        return self.workspace.root

    def rule_pack_name(self, override: str | None = None) -> str:
        try:
            return resolve_pack(override or self.rules).name
        except Exception:  # noqa: BLE001 - reported as a problem by the caller that needs it
            return "unavailable"

    def _rules_for(self, query: dict[str, list[str]]) -> str | None:
        """``?rules=`` overrides the pack for one request only (spec §3.9)."""
        values = query.get("rules")
        if not values:
            return self.rules
        wanted = values[0].strip()
        if not wanted:
            raise ApiProblem("invalid_query", "'rules' must not be empty", parameter="rules")
        if wanted not in available_packs() and not wanted.endswith(".json"):
            raise ApiProblem(
                "invalid_query",
                f"unknown rule pack {wanted!r}",
                parameter="rules",
                available=available_packs(),
            )
        return wanted

    def _audit(self, request_id: str, transaction_id: str, outcome: str, detail=None) -> None:
        payload = {"request_id": request_id}
        if detail:
            payload.update(detail)
        self.workspace.audit_logger().record(SERVICE_NAME, transaction_id, outcome, payload)

    # -- dispatch ----------------------------------------------------------------------

    def dispatch(self, method: str, raw_path: str, body: bytes, request_id: str) -> Response:
        parsed = urlparse(raw_path)
        path = parsed.path.rstrip("/") or "/"
        # keep_blank_values: `?rules=` must reach the validator as an empty value, not vanish.
        query = parse_qs(parsed.query, keep_blank_values=True)

        path_matched = False
        allowed: list[str] = []
        for route in self.ROUTES:
            match = route.pattern.match(path)
            if not match:
                continue
            path_matched = True
            allowed.append(route.method)
            if route.method == method:
                handler: Callable[..., Response] = getattr(self, route.handler)
                return handler(
                    params=match.groupdict(),
                    query=query,
                    body=body,
                    request_id=request_id,
                    path=path,
                )

        if path_matched:
            allow = ", ".join(sorted(set(allowed + ["OPTIONS"])))
            raise ApiProblem(
                "method_not_allowed",
                f"{method} is not allowed on {path}",
                allow=allow,
                allowed_methods=sorted(set(allowed)),
            )
        raise ApiProblem("not_found", f"no route for {path}")

    # -- handlers ----------------------------------------------------------------------

    def handle_presentation(self, **_kwargs: Any) -> Response:
        """Serve the interactive presentation from the API itself.

        Same-origin is the point: the page can then drive the real endpoints with no CORS dance and
        no configuration, which is what makes "run the demo from the HTML" work out of the box.
        """
        page = PROJECT_ROOT / "docs" / "presentation.html"
        if not page.exists():
            raise ApiProblem("not_found", "docs/presentation.html is not present")
        return Response(
            200, text=page.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8"
        )

    def handle_health(self, **_kwargs: Any) -> Response:
        return Response(
            200,
            {
                "status": "ok",
                "service": SERVICE_NAME,
                "api_version": API_VERSION,
                "workspace": self.shared_root.name,
                "rule_pack": self.rule_pack_name(),
                "available_rule_packs": available_packs(),
                "pipeline_agents": [agent.name for agent in _pipeline_agents()],
                "uptime_seconds": round(time.monotonic() - self.started_at, 3),
                "results": len(results_store.load_results(self.shared_root)),
            },
        )

    def handle_rules(self, query: dict[str, list[str]], **_kwargs: Any) -> Response:
        pack = resolve_pack(self._rules_for(query))  # RuleError -> rule_pack_unavailable, centrally
        return Response(200, pack.as_dict())

    def handle_errors(self, **_kwargs: Any) -> Response:
        """The catalog itself, so a client can generate its own handling from the source of truth."""
        from .errors import CATALOG

        return Response(
            200,
            {
                "problem_format": "RFC 9457",
                "content_type": PROBLEM_CONTENT_TYPE,
                "errors": [
                    {
                        "code": definition.code,
                        "status": definition.status,
                        "title": definition.title,
                        "type": definition.type_uri,
                        "client_fault": definition.client_fault,
                        "retryable": definition.retryable,
                    }
                    for definition in sorted(CATALOG.values(), key=lambda d: (d.status, d.code))
                ],
            },
        )

    def handle_submit(
        self,
        body: bytes,
        query: dict[str, list[str]],
        request_id: str,
        path: str,
        **_kwargs: Any,
    ) -> Response:
        payload = _parse_json(body)
        if isinstance(payload, list):
            raise ApiProblem(
                "invalid_body", "send an array to /transactions/batch, not /transactions"
            )
        # Schema first (400), business verdict second (422/409) — see gateway/validation.py.
        ensure_valid_submission(payload)

        rules = self._rules_for(query)
        outcome = self._run_one(payload, rules, request_id)
        location = f"/transactions/{outcome['transaction_id']}"

        problem = verdict_problem(outcome, path=path)
        if problem is not None:
            # The result is stored and retrievable; Location still points at it.
            problem.extensions.setdefault("location", location)
            raise problem
        return Response(201, outcome, headers={"Location": location})

    def handle_submit_batch(
        self, body: bytes, query: dict[str, list[str]], request_id: str, path: str, **_kwargs: Any
    ) -> Response:
        payload = _parse_json(body)
        if isinstance(payload, dict):
            payload = payload.get("transactions")
        if not isinstance(payload, list):
            raise ApiProblem(
                "invalid_body", "expected an array, or an object with a 'transactions' array"
            )
        if not payload:
            raise ApiProblem("invalid_body", "'transactions' must not be empty")
        if len(payload) > MAX_BATCH:
            raise ApiProblem(
                "invalid_body", f"batch of {len(payload)} exceeds the limit of {MAX_BATCH}"
            )

        rules = self._rules_for(query)
        items: list[dict[str, Any]] = []
        counts: dict[str, int] = {}

        for index, candidate in enumerate(payload):
            # A batch never fails as a whole: each item reports its own status, so one bad row
            # cannot discard the outcomes of the rows that were processed.
            try:
                ensure_valid_submission(candidate)
                outcome = self._run_one(candidate, rules, request_id)
            except ApiProblem as problem:
                items.append(
                    {
                        "index": index,
                        "transaction_id": _safe_id(candidate),
                        "http_status": problem.status,
                        "status": "error",
                        "problem": problem.document(
                            instance=f"{path}[{index}]", request_id=request_id
                        ),
                    }
                )
                counts["error"] = counts.get("error", 0) + 1
                continue

            status = str(outcome["status"])
            verdict = verdict_problem(outcome, path=path)
            item = {
                "index": index,
                "transaction_id": outcome["transaction_id"],
                "http_status": 201 if verdict is None else verdict.status,
                "status": status,
                "outcome": outcome,
            }
            if verdict is not None:
                # A non-settled row carries the same problem document a single submission would get,
                # so a client can handle batch and single responses with one code path.
                item["problem"] = verdict.document(
                    instance=f"{path}[{index}]", request_id=request_id
                )
            items.append(item)
            counts[status] = counts.get(status, 0) + 1

        # 201 when every item settled, 207 when the batch is mixed — the aggregate status must not
        # claim success for rows that were rejected or held.
        all_created = all(item["http_status"] == 201 for item in items)
        return Response(
            201 if all_created else 207,
            {
                "submitted": len(items),
                "by_status": dict(sorted(counts.items())),
                "results": items,
            },
        )

    def handle_agents(self, **_kwargs: Any) -> Response:
        """Discovery: which agents exist, what each reads, where each routes (CR-02)."""
        return Response(
            200,
            {
                "count": len(AGENT_SERVICES),
                "transport": "file protocol is the journal; these routes are stateless calls",
                "agents": describe_agents(),
            },
        )

    def handle_agent_process(
        self,
        params: dict[str, str],
        body: bytes,
        query: dict[str, list[str]],
        request_id: str,
        **_kwargs: Any,
    ) -> Response:
        """Run a single agent as a service. Stateless: nothing is written to ``shared/``."""
        agent_name = params["agent_name"]
        payload = _parse_json(body)
        rules = self._rules_for(query)
        result = invoke(
            agent_name,
            payload,
            workspace=self.workspace,
            audit=self.workspace.audit_logger(),
            rules=rules,
        )
        self._audit(
            request_id,
            str(((result["message"].get("data")) or {}).get("transaction_id", "UNKNOWN")),
            "agent_invoked",
            {"agent": agent_name, "next_agent": result["next_agent"]},
        )
        return Response(200, result)

    def handle_chain(
        self, body: bytes, query: dict[str, list[str]], request_id: str, **_kwargs: Any
    ) -> Response:
        """Drive one payload through every agent as service calls, writing nothing (CR-02)."""
        payload = _parse_json(body)
        rules = self._rules_for(query)
        result = chain(
            payload,
            workspace=self.workspace,
            audit=self.workspace.audit_logger(),
            rules=rules,
        )
        self._audit(
            request_id,
            str(((result["message"].get("data")) or {}).get("transaction_id", "UNKNOWN")),
            "chain_invoked",
            {"agents_invoked": result["agents_invoked"], "final_status": result["final_status"]},
        )
        return Response(200, result)

    def handle_list(self, **_kwargs: Any) -> Response:
        return Response(200, results_store.list_pipeline_results(self.shared_root))

    def handle_get(self, params: dict[str, str], **_kwargs: Any) -> Response:
        transaction_id = params["transaction_id"]
        status = results_store.get_transaction_status(transaction_id, self.shared_root)
        if not status.get("found"):
            raise ApiProblem(
                "transaction_not_found",
                f"no result for {transaction_id!r}",
                transaction_id=transaction_id,
            )
        return Response(200, status)

    def handle_run_sample(
        self, query: dict[str, list[str]], request_id: str, **_kwargs: Any
    ) -> Response:
        # The input file is deliberately NOT caller-controlled: accepting a path over HTTP would
        # turn this endpoint into an arbitrary-file-read primitive.
        rules = self._rules_for(query)
        with self._lock:
            summary = run_pipeline(
                self.sample_path, self.shared_root, reset=True, verbose=False, rules=rules
            )
        self._audit(request_id, "ALL", "sample_run", {"rule_pack": self.rule_pack_name(rules)})
        return Response(200, summary)

    def handle_summary(self, **_kwargs: Any) -> Response:
        return Response(200, ReportingAgent(self.workspace).build_summary())

    def handle_summary_markdown(self, **_kwargs: Any) -> Response:
        markdown = render_markdown(ReportingAgent(self.workspace).build_summary())
        return Response(200, text=markdown, content_type=MARKDOWN_CONTENT_TYPE)

    def handle_audit(self, query: dict[str, list[str]], **_kwargs: Any) -> Response:
        limit = _int_param(query, "limit", AUDIT_DEFAULT_LIMIT, 1, AUDIT_MAX_LIMIT)
        entries = self.workspace.audit_logger().entries()
        return Response(200, {"total": len(entries), "limit": limit, "entries": entries[-limit:]})

    # -- pipeline ----------------------------------------------------------------------

    def _run_one(self, transaction: dict[str, Any], rules: str | None, request_id: str) -> dict[str, Any]:
        transaction_id = str(transaction.get("transaction_id", "UNKNOWN"))
        self._audit(
            request_id,
            transaction_id,
            "submitted",
            {"rule_pack": self.rule_pack_name(rules), "transport": self.transport},
        )
        if self.transport == "rest":
            return self._run_via_services(transaction, rules, request_id)
        # Drains claim files on disk, so only one may run at a time (spec §3.9, edge case EC-24).
        with self._lock:
            message, trace = submit_transaction_traced(self.workspace, transaction, rules=rules)
        return {
            **results_store.summarise_result(message),
            "transport": "inprocess",
            "trace": trace,
        }

    def _run_via_services(
        self, transaction: dict[str, Any], rules: str | None, request_id: str
    ) -> dict[str, Any]:
        """Hand the transaction to the first agent service; the chain forwards itself (CR-02).

        No lock here: each service is idempotent on ``message_id`` and owns its own concurrency, which
        is the point of splitting them out in the first place.
        """
        from agents.protocol import build_message
        from services.client import TransportError, post_json

        topology = self.topology
        entry = topology.first
        message = build_message(
            source_agent="api_gateway",
            target_agent=entry.name,
            message_type="transaction",
            data=dict(transaction),
        )
        headers = {"X-Request-Id": request_id}
        if rules:
            # The pack lives inside the long-running policy service, so the override travels with the
            # request and is forwarded hop to hop (see services/agent_service.py).
            headers["X-Policy-Rules"] = rules
        try:
            reply = post_json(entry.process_url, message, headers=headers)
        except TransportError as exc:
            raise ApiProblem(
                "upstream_unavailable",
                f"the agent chain could not be reached: {exc.detail}",
                entrypoint=entry.name,
                attempts=exc.attempts,
            ) from exc

        body = reply.payload if isinstance(reply.payload, dict) else {}
        outcome = body.get("outcome")
        if not isinstance(outcome, dict):
            raise ApiProblem(
                "pipeline_error",
                "the agent chain returned no terminal outcome",
                downstream_status=reply.status,
            )
        return {**outcome, "transport": "rest", "trace": body.get("trace", [])}


def _pipeline_agents():
    from agents import PIPELINE_AGENTS

    return PIPELINE_AGENTS


def _safe_id(candidate: Any) -> str | None:
    if isinstance(candidate, dict):
        value = candidate.get("transaction_id")
        return str(value) if isinstance(value, str) else None
    return None


def _parse_json(body: bytes) -> Any:
    if not body:
        raise ApiProblem("invalid_body", "a request body is required")
    try:
        return json.loads(body.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ApiProblem("invalid_json", "body must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ApiProblem(
            "invalid_json", f"malformed JSON: {exc.msg}", line=exc.lineno, column=exc.colno
        ) from exc


def _int_param(
    query: dict[str, list[str]], name: str, default: int, minimum: int, maximum: int
) -> int:
    values = query.get(name)
    if not values:
        return default
    try:
        value = int(values[0])
    except ValueError as exc:
        raise ApiProblem("invalid_query", f"{name!r} must be an integer", parameter=name) from exc
    if not minimum <= value <= maximum:
        raise ApiProblem(
            "invalid_query",
            f"{name!r} must be between {minimum} and {maximum}",
            parameter=name,
        )
    return value


# --------------------------------------------------------------------------------------
# HTTP plumbing
# --------------------------------------------------------------------------------------


class GatewayHandler(BaseHTTPRequestHandler):
    """Thin translation layer between ``http.server`` and :class:`PipelineGateway`."""

    pipeline_gateway: PipelineGateway
    server_version = f"{SERVICE_NAME}/{API_VERSION}"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # -- verbs -------------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - name mandated by BaseHTTPRequestHandler
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle("PATCH")

    def do_OPTIONS(self) -> None:  # noqa: N802
        """CORS preflight. A JSON POST from a file:// page is never "simple", so this must answer."""
        self._send(
            Response(
                204,
                headers={
                    "Allow": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, X-Policy-Rules, X-Request-Id",
                    "Access-Control-Max-Age": "600",
                },
            ),
            request_id=self._new_request_id(),
        )

    # -- the single error funnel --------------------------------------------------------

    def _handle(self, method: str) -> None:
        request_id = self._new_request_id()
        started = time.monotonic()
        path = urlparse(self.path).path or "/"

        try:
            body = self._read_body()
            response = self.pipeline_gateway.dispatch(method, self.path, body, request_id)
        except BaseException as exc:  # noqa: BLE001 - every failure leaves through here
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):  # pragma: no cover
                raise
            response = self._problem_response(exc, path=path, request_id=request_id)

        self._send(response, request_id=request_id)
        self._log_access(method, response.status, started, request_id)

    def _problem_response(self, exc: BaseException, *, path: str, request_id: str) -> Response:
        problem = problem_from_exception(exc)
        if not problem.definition.client_fault:
            # Log the real cause; the client gets the catalog's generic detail (guardrail IN-10).
            self.log_error("%s: %r", problem.code, exc)

        headers = {}
        allow = problem.extensions.pop("allow", None)
        if allow:
            headers["Allow"] = str(allow)
        location = problem.extensions.pop("location", None)
        if location:
            headers["Location"] = str(location)

        return Response(
            problem.status,
            problem.document(instance=path, request_id=request_id),
            headers=headers or None,
            content_type=PROBLEM_CONTENT_TYPE,
        )

    def _read_body(self) -> bytes:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return b""
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ApiProblem("invalid_body", "Content-Length must be an integer") from exc
        if length < 0:
            raise ApiProblem("invalid_body", "Content-Length must not be negative")
        if length > MAX_BODY_BYTES:
            # Never buffer an oversized body — but do drain it, up to a hard ceiling, so the client
            # can finish writing and read our 413 instead of hitting a broken pipe. Past the ceiling
            # the connection is dropped, which is the only sane answer to an absurd Content-Length.
            self._drain(length)
            raise ApiProblem(
                "payload_too_large",
                f"body of {length} bytes exceeds the {MAX_BODY_BYTES} byte limit",
                limit_bytes=MAX_BODY_BYTES,
            )
        return self.rfile.read(length)

    def _drain(self, length: int) -> None:
        if length > DRAIN_CEILING_BYTES:
            self.close_connection = True
            return
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def _send(self, response: Response, request_id: str) -> None:
        if response.text is not None:
            body = response.text.encode("utf-8")
        elif response.payload is None:
            body = b""
        else:
            # Final PII guard on the way out (guardrail IN-10).
            assert_no_plaintext_pii(response.payload, where="response")
            body = json.dumps(response.payload, indent=2, ensure_ascii=False).encode("utf-8")

        self.send_response(response.status)
        self.send_header("X-Request-Id", request_id)
        # Permissive CORS, deliberately: the presentation must work when opened as a file:// page too.
        # This is a loopback-only demo surface with no credentials — see CR-02 §5 and docs/errors.md.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "X-Request-Id, Location")
        if body:
            self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (response.headers or {}).items():
            if name.lower() not in ("content-length", "content-type"):
                self.send_header(name, value)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    @staticmethod
    def _new_request_id() -> str:
        return uuid.uuid4().hex[:12]

    def _log_access(self, method: str, status: int, started: float, request_id: str) -> None:
        duration_ms = (time.monotonic() - started) * 1000
        sys.stderr.write(
            f"[{SERVICE_NAME}] {method} {self.path} -> {status} "
            f"{duration_ms:.1f}ms req={request_id}\n"
        )
        sys.stderr.flush()

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        """Silence the default per-request line; :meth:`_log_access` is the one line we want."""


# --------------------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------------------


def create_server(
    gateway: PipelineGateway, host: str = "127.0.0.1", port: int = 0
) -> ThreadingHTTPServer:
    """Bind a threading HTTP server. ``port=0`` picks a free port, which tests rely on."""

    class BoundHandler(GatewayHandler):
        pipeline_gateway = gateway

    server = ThreadingHTTPServer((host, port), BoundHandler)
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="REST gateway for the banking pipeline")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080, help="0 picks a free port")
    parser.add_argument("--shared", default=str(PROJECT_ROOT / "shared"))
    parser.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    parser.add_argument(
        "--rules",
        default=None,
        help=f"default policy rule pack (available: {', '.join(available_packs())})",
    )
    parser.add_argument(
        "--transport",
        choices=PipelineGateway.TRANSPORTS,
        default="inprocess",
        help="inprocess drains the agents here; rest hands off to the agent service mesh (CR-02)",
    )
    parser.add_argument("--topology", default=None, help="topology JSON for --transport rest")
    args = parser.parse_args(argv)

    topology = None
    if args.transport == "rest":
        from services.topology import load_topology

        topology = load_topology(args.topology)

    gateway = PipelineGateway(
        args.shared, args.sample, args.rules, transport=args.transport, topology=topology
    )
    server = create_server(gateway, args.host, args.port)
    host, port = server.server_address[:2]

    # demo.sh parses this line to learn the port when it asked for 0.
    print(f"{SERVICE_NAME} listening on http://{host}:{port}", flush=True)
    print(f"  workspace : {gateway.shared_root}", flush=True)
    print(f"  rule pack : {gateway.rule_pack_name()}", flush=True)
    print(f"  transport : {gateway.transport}", flush=True)
    print(f"  routes    : {len(PipelineGateway.ROUTES)}", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{SERVICE_NAME} stopping", flush=True)
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
