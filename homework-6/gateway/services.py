"""Each agent exposed as a callable service (CR-02, spec task T-17).

The file protocol stays the durable journal — it is what makes a run auditable and replayable, and it
is what produces the §8 baseline. On top of it, every agent is *also* reachable as a stateless HTTP
service: ``POST /agents/{name}/process`` takes a message, returns the message the agent emits, and
touches no file.

That works because :meth:`agents.base.BaseAgent.process_message` was already pure with respect to the
filesystem — only :meth:`~agents.base.BaseAgent.run` claims and writes files. So "agent as a
microservice" needs no rewrite of the agents; it needs an adapter, which is this module.

Two shapes of input are accepted:

* a **full protocol message** — used as-is, so a caller can hand one agent's output straight to the
  next agent and chain the pipeline over HTTP;
* a **bare payload object** — wrapped in a message addressed to the agent, for convenience.
"""

from __future__ import annotations

from typing import Any

from agents import PIPELINE_AGENTS
from agents.protocol import (
    MESSAGE_FIELDS,
    TERMINAL_TARGET,
    MoneyError,
    ProtocolError,
    build_message,
    validate_message,
)

from .errors import ApiProblem

#: Agent name -> agent class, in pipeline order. The single registry the HTTP surface reads.
AGENT_SERVICES: dict[str, type] = {agent.name: agent for agent in PIPELINE_AGENTS}

#: Where a message goes after each agent, for the discovery endpoint. Read from the agent modules so
#: it cannot drift from the actual routing constants.
def _next_agent_of(agent_class: type) -> str | None:
    module = __import__(agent_class.__module__, fromlist=["NEXT_AGENT"])
    return getattr(module, "NEXT_AGENT", None)


def describe_agents() -> list[dict[str, Any]]:
    """The agent catalog: what exists, what it reads, where it routes."""
    return [
        {
            "name": name,
            "position": index + 1,
            "inbox": agent_class.inbox,
            "next_agent": _next_agent_of(agent_class),
            "route": f"/agents/{name}/process",
            "summary": (agent_class.__doc__ or "").strip().splitlines()[0]
            if agent_class.__doc__
            else "",
        }
        for index, (name, agent_class) in enumerate(AGENT_SERVICES.items())
    ]


def _looks_like_message(payload: Any) -> bool:
    return isinstance(payload, dict) and all(field in payload for field in MESSAGE_FIELDS)


def wrap_input(agent_name: str, payload: Any) -> dict[str, Any]:
    """Coerce a request body into a protocol message addressed to ``agent_name``."""
    if not isinstance(payload, dict):
        raise ApiProblem("invalid_body", "expected a JSON object: a message or a payload")

    if _looks_like_message(payload):
        try:
            validate_message(payload)
        except ProtocolError as exc:
            raise ApiProblem("validation_failed", f"invalid protocol message: {exc}") from exc
        return payload

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return build_message(
        source_agent="api_client",
        target_agent=agent_name,
        message_type="transaction",
        data=data,
    )


def build_agent(agent_name: str, workspace, audit=None, rules=None):
    """Instantiate one agent for a stateless call."""
    try:
        agent_class = AGENT_SERVICES[agent_name]
    except KeyError as exc:
        raise ApiProblem(
            "not_found",
            f"no agent named {agent_name!r}",
            available_agents=sorted(AGENT_SERVICES),
        ) from exc

    from agents import PolicyEngine

    if agent_class is PolicyEngine:
        return agent_class(workspace, audit, pack=rules)
    return agent_class(workspace, audit)


def invoke(agent_name: str, payload: Any, *, workspace, audit=None, rules=None) -> dict[str, Any]:
    """Run one agent over one message and return what it emitted. Writes nothing."""
    agent = build_agent(agent_name, workspace, audit, rules)
    message = wrap_input(agent_name, payload)

    if message["target_agent"] != agent_name:
        raise ApiProblem(
            "invalid_body",
            f"message is addressed to {message['target_agent']!r}, not {agent_name!r}",
            addressed_to=message["target_agent"],
        )

    try:
        emitted = agent.process_message(message)
        validate_message(emitted)
    except (MoneyError, ProtocolError, KeyError, ValueError) as exc:
        # The agent could not make sense of the payload. That is the caller's problem, not a 500 —
        # and the detail is our own text, never an upstream traceback (guardrail IN-10).
        raise ApiProblem(
            "validation_failed",
            f"{agent_name} could not process the message: {exc}",
            agent=agent_name,
        ) from exc

    data = emitted.get("data") or {}
    return {
        "agent": agent_name,
        "input_status": (message.get("data") or {}).get("status"),
        "status": data.get("status"),
        "next_agent": emitted["target_agent"],
        "terminal": emitted["target_agent"] == TERMINAL_TARGET,
        "message": emitted,
    }


def chain(payload: Any, *, workspace, audit=None, rules=None) -> dict[str, Any]:
    """Drive one payload through every agent in memory, hop by hop.

    This is the file protocol's route expressed as service calls: each hop feeds the previous hop's
    output message to the next agent, stopping when a message is terminal. Nothing is written, so it
    is a dry run of the pipeline rather than a replacement for it.
    """
    first = next(iter(AGENT_SERVICES))
    message = wrap_input(first, payload)
    hops: list[dict[str, Any]] = []
    current = message
    terminal: dict[str, Any] | None = None

    for _ in range(len(AGENT_SERVICES)):
        target = current["target_agent"]
        if target == TERMINAL_TARGET:
            break
        if target not in AGENT_SERVICES:
            raise ApiProblem(
                "pipeline_error", f"message routed to unknown agent {target!r}", routed_to=target
            )
        result = invoke(target, current, workspace=workspace, audit=audit, rules=rules)
        hops.append(
            {
                "agent": result["agent"],
                "status": result["status"],
                "next_agent": result["next_agent"],
                "terminal": result["terminal"],
            }
        )
        current = result["message"]
        if result["terminal"]:
            terminal = current
            break

    return {
        "hops": hops,
        "agents_invoked": len(hops),
        "terminal": terminal is not None,
        "final_status": (((terminal or current).get("data")) or {}).get("status"),
        "message": terminal or current,
    }
