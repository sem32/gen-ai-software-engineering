"""One agent, one HTTP service (CR-02.1, spec task T-17).

Each service wraps **the existing agent class unchanged** — it imports
:meth:`agents.base.BaseAgent.process_message` rather than reimplementing a decision — and adds the
three things a network hop needs that a file drop did not:

* it **forwards** the emitted message to its successor's ``/process`` over HTTP (choreography: the
  services talk to each other, no central coordinator),
* it is **idempotent** on ``message_id``, because a retried hop must not process twice or write a
  second result file,
* it writes to the **file journal** — the audit trail for every hop, and the terminal result for the
  last hop. That is the "files under the hood for logging" part of CR-02.

The chain is synchronous: a service returns whatever came back from downstream, so the terminal verdict
unwinds to the original caller and a single ``POST`` still answers with the final outcome.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from agents.protocol import TERMINAL_TARGET, Workspace, transaction_id_of, validate_message  # noqa: E402
from gateway.errors import (  # noqa: E402
    PROBLEM_CONTENT_TYPE,
    ApiProblem,
    problem_document,
    problem_from_exception,
    verdict_problem,
)
from gateway.services import build_agent  # noqa: E402

from .client import TransportError, post_json  # noqa: E402
from .topology import Topology, load_topology  # noqa: E402

JSON_CONTENT_TYPE = "application/json; charset=utf-8"


class AgentService:
    """The service behind one agent."""

    def __init__(
        self,
        agent_name: str,
        workspace: Workspace,
        topology: Topology,
        rules: str | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.workspace = workspace
        self.topology = topology
        self.rules = rules
        self.spec = topology.get(agent_name)
        self.audit = workspace.audit_logger()
        self.agent = build_agent(agent_name, workspace, self.audit, rules)
        self.started_at = time.monotonic()
        self._lock = threading.Lock()
        self._idempotency_dir = workspace.root / "processed" / agent_name
        self._idempotency_dir.mkdir(parents=True, exist_ok=True)

    # -- health ------------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "agent": self.agent_name,
            "position": self.spec.position,
            "inbox_transport": "rest",
            "next": self.spec.next_name,
            "next_url": self.topology.next_url_of(self.agent_name),
            "rule_pack": getattr(self.agent, "pack_name", None),
            "uptime_seconds": round(time.monotonic() - self.started_at, 3),
            "processed": len(list(self._idempotency_dir.glob("*.json"))),
        }

    # -- idempotency -------------------------------------------------------------------

    def _cache_path(self, message_id: str) -> Path:
        safe = "".join(char for char in message_id if char.isalnum() or char in "-_")[:64]
        return self._idempotency_dir / f"{safe}.json"

    def _cached(self, message_id: str) -> tuple[int, dict[str, Any]] | None:
        path = self._cache_path(message_id)
        if not path.exists():
            return None
        stored = json.loads(path.read_text(encoding="utf-8"))
        return int(stored["status"]), stored["body"]

    def _remember(self, message_id: str, status: int, body: dict[str, Any]) -> None:
        self._cache_path(message_id).write_text(
            json.dumps({"status": status, "body": body}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # -- the hop -----------------------------------------------------------------------

    def process(
        self, message: Any, request_id: str, rules_override: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        """Run this agent over ``message`` and return ``(http_status, body)``.

        ``rules_override`` arrives as the ``X-Policy-Rules`` header and is forwarded along the chain,
        so a caller can select a rule pack per request even though the pack lives in a long-running
        service (spec §3.9).
        """
        if not isinstance(message, dict):
            raise ApiProblem("invalid_body", "expected a protocol message object")
        try:
            validate_message(message)
        except Exception as exc:  # noqa: BLE001 - mapped centrally below
            raise ApiProblem("validation_failed", f"invalid protocol message: {exc}") from exc

        if message["target_agent"] != self.agent_name:
            raise ApiProblem(
                "invalid_body",
                f"message is addressed to {message['target_agent']!r}, not {self.agent_name!r}",
                addressed_to=message["target_agent"],
            )

        # The rule pack is part of the identity of a call: the same message under a different pack is
        # a different question, so it must not hit the cached answer.
        cache_key = f"{message['message_id']}--{rules_override or 'default'}"
        with self._lock:
            replay = self._cached(cache_key)
            if replay is not None:
                status, body = replay
                body = {**body, "idempotent_replay": True}
                self.audit.record(
                    self.agent_name,
                    transaction_id_of(message),
                    "idempotent_replay",
                    {"request_id": request_id, "message_id": str(message["message_id"])[:8]},
                )
                return status, body

            status, body = self._process_once(message, request_id, rules_override)
            self._remember(cache_key, status, body)
            return status, body

    def _agent_for(self, rules_override: str | None):
        """The long-lived agent, or a per-request one when the caller overrode the rule pack."""
        if not rules_override or rules_override == self.rules:
            return self.agent
        return build_agent(self.agent_name, self.workspace, self.audit, rules_override)

    def _process_once(
        self, message: dict[str, Any], request_id: str, rules_override: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        emitted = self._agent_for(rules_override).process_message(message)
        validate_message(emitted)

        transaction_id = transaction_id_of(emitted)
        data = emitted.get("data") or {}
        status_name = str(data.get("status", "unknown"))
        terminal = emitted["target_agent"] == TERMINAL_TARGET

        # Audit before anything irreversible (spec §3.3) — the journal is still files (CR-02).
        self.audit.record(
            self.agent_name,
            transaction_id,
            status_name,
            {
                "request_id": request_id,
                "hop": self.spec.position,
                "transport": "rest",
                "next_agent": emitted["target_agent"],
            },
        )

        hop = {
            "agent": self.agent_name,
            "position": self.spec.position,
            "status": status_name,
            "next": emitted["target_agent"],
            "terminal": terminal,
        }

        if terminal:
            return self._finish(emitted, hop, request_id)
        return self._forward(emitted, hop, request_id, rules_override)

    def _finish(
        self, emitted: dict[str, Any], hop: dict[str, Any], request_id: str
    ) -> tuple[int, dict[str, Any]]:
        """Terminal outcome: write the result file, then answer with the verdict."""
        from agents import results_store

        self.workspace.write_message(self.workspace.results_dir, emitted, require_masked=True)
        outcome = results_store.summarise_result(emitted)

        problem = verdict_problem(outcome, path=f"/agents/{self.agent_name}/process")
        if problem is not None:
            document = problem.document(
                instance=f"/agents/{self.agent_name}/process", request_id=request_id
            )
            document["trace"] = [hop]
            return problem.status, document

        return 200, {
            "terminal": True,
            "final_status": outcome["status"],
            "outcome": outcome,
            "trace": [hop],
        }

    def _forward(
        self,
        emitted: dict[str, Any],
        hop: dict[str, Any],
        request_id: str,
        rules_override: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Hand the message to the successor service over HTTP."""
        next_url = self.topology.next_url_of(self.agent_name)
        if next_url is None:
            # Non-terminal message with nowhere to go: loud failure, never a silent drop.
            raise ApiProblem(
                "pipeline_error",
                f"{self.agent_name} produced a non-terminal message but has no successor",
                next_agent=emitted["target_agent"],
            )

        try:
            headers = {"X-Request-Id": request_id}
            if rules_override:
                # The override must survive every hop, or the policy service would not see it.
                headers["X-Policy-Rules"] = rules_override
            result = post_json(next_url, emitted, headers=headers)
        except TransportError as exc:
            self.audit.record(
                self.agent_name,
                transaction_id_of(emitted),
                "forward_failed",
                {"request_id": request_id, "next_url": next_url, "attempts": exc.attempts},
            )
            raise ApiProblem(
                "upstream_unavailable",
                f"could not reach {emitted['target_agent']}: {exc.detail}",
                next_agent=emitted["target_agent"],
                attempts=exc.attempts,
            ) from exc

        body = result.payload if isinstance(result.payload, dict) else {"downstream": result.payload}
        # Prepend our hop so the trace reads first-to-last once it unwinds to the caller.
        body["trace"] = [hop, *body.get("trace", [])]
        return result.status, body


# --------------------------------------------------------------------------------------
# HTTP plumbing
# --------------------------------------------------------------------------------------


class AgentServiceHandler(BaseHTTPRequestHandler):
    """Two routes: ``GET /health`` and ``POST /process``."""

    service: AgentService
    server_version = "agent-service/2.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("/health", ""):
            self._respond(200, self.service.health(), JSON_CONTENT_TYPE, self._request_id())
            return
        self._fail(ApiProblem("not_found", f"no route for {self.path}"))

    def do_POST(self) -> None:  # noqa: N802
        request_id = self.headers.get("X-Request-Id") or self._request_id()
        if self.path.rstrip("/") != "/process":
            self._fail(ApiProblem("not_found", f"no route for {self.path}"), request_id)
            return
        try:
            body = self._read_body()
            payload = json.loads(body.decode("utf-8")) if body else None
            rules_override = self.headers.get("X-Policy-Rules")
            status, response = self.service.process(payload, request_id, rules_override)
        except json.JSONDecodeError as exc:
            self._fail(ApiProblem("invalid_json", f"malformed JSON: {exc.msg}"), request_id)
        except BaseException as exc:  # noqa: BLE001 - single funnel, like the gateway
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):  # pragma: no cover
                raise
            self._fail(exc, request_id)
        else:
            content_type = PROBLEM_CONTENT_TYPE if status >= 400 else JSON_CONTENT_TYPE
            self._respond(status, response, content_type, request_id)

    # -- helpers -----------------------------------------------------------------------

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def _fail(self, exc: BaseException, request_id: str | None = None) -> None:
        request_id = request_id or self._request_id()
        problem = problem_from_exception(exc)
        if not problem.definition.client_fault:
            self.log_error("%s: %r", problem.code, exc)
        document = problem.document(instance=self.path, request_id=request_id)
        self._respond(problem.status, document, PROBLEM_CONTENT_TYPE, request_id)

    def _respond(self, status: int, payload: Any, content_type: str, request_id: str) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-Id", request_id)
        self.send_header("X-Agent", getattr(self.service, "agent_name", "unknown"))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _request_id() -> str:
        return uuid.uuid4().hex[:12]

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write(
            f"[{getattr(self.service, 'agent_name', '?')}] {self.command} {self.path} "
            f"{fmt % args}\n"
        )
        sys.stderr.flush()


def create_service_server(service: AgentService, host: str, port: int) -> ThreadingHTTPServer:
    class BoundHandler(AgentServiceHandler):
        pass

    BoundHandler.service = service
    server = ThreadingHTTPServer((host, port), BoundHandler)
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one pipeline agent as an HTTP service")
    parser.add_argument("--agent", required=True, help="agent name, e.g. fraud_detector")
    parser.add_argument("--shared", default=str(PROJECT_ROOT / "shared"))
    parser.add_argument("--topology", default=None, help="path to a topology JSON file")
    parser.add_argument("--rules", default=None, help="policy rule pack (policy_engine only)")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)

    topology = load_topology(args.topology)
    spec = topology.get(args.agent)
    workspace = Workspace.create(args.shared)
    service = AgentService(args.agent, workspace, topology, args.rules)

    server = create_service_server(service, args.host or spec.host, args.port or spec.port)
    host, port = server.server_address[:2]
    print(
        f"agent-service {args.agent} listening on http://{host}:{port} "
        f"-> next={spec.next_name}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"agent-service {args.agent} stopping", flush=True)
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
