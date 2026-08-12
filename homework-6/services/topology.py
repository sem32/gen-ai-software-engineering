"""Service topology — who talks to whom (CR-02, spec task T-17).

Nothing about the chain is hardcoded inside an agent. A service is told its own name, its port and its
successor's URL; this module is the one place that knows the default wiring, and it is derived from
``PIPELINE_AGENTS`` so the REST chain cannot drift from the in-process order.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents import PIPELINE_AGENTS

DEFAULT_HOST = "127.0.0.1"
#: Base port; each agent gets ``BASE_PORT + position``. Overridable so tests never collide.
BASE_PORT = 8801
PORT_ENV_VAR = "HW6_SERVICE_BASE_PORT"
TOPOLOGY_ENV_VAR = "HW6_TOPOLOGY"

#: Sentinel successor: the last service in the chain writes the result file instead of forwarding.
SINK = "results"


@dataclass(frozen=True)
class ServiceSpec:
    """One agent service."""

    name: str
    position: int
    host: str
    port: int
    next_name: str

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def process_url(self) -> str:
        return f"{self.base_url}/process"

    @property
    def health_url(self) -> str:
        return f"{self.base_url}/health"

    @property
    def is_terminal_hop(self) -> bool:
        return self.next_name == SINK

    def as_dict(self) -> dict[str, Any]:
        # host and port are what `load_topology` reads back; `url` is for humans reading the JSON.
        return {
            "name": self.name,
            "position": self.position,
            "host": self.host,
            "port": self.port,
            "url": self.base_url,
            "next": self.next_name,
        }


@dataclass(frozen=True)
class Topology:
    """The whole chain, in order."""

    services: tuple[ServiceSpec, ...]

    def __post_init__(self) -> None:
        if not self.services:
            raise ValueError("a topology needs at least one service")

    @property
    def first(self) -> ServiceSpec:
        return self.services[0]

    def get(self, name: str) -> ServiceSpec:
        for service in self.services:
            if service.name == name:
                return service
        known = ", ".join(service.name for service in self.services)
        raise KeyError(f"unknown service {name!r}; known services: {known}")

    def next_url_of(self, name: str) -> str | None:
        """The successor's ``/process`` URL, or ``None`` when this service is the terminal hop."""
        service = self.get(name)
        if service.is_terminal_hop:
            return None
        return self.get(service.next_name).process_url

    def as_dict(self) -> dict[str, Any]:
        return {
            "services": [service.as_dict() for service in self.services],
            "entrypoint": self.first.process_url,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2)


def default_topology(host: str = DEFAULT_HOST, base_port: int | None = None) -> Topology:
    """Derive the chain from ``PIPELINE_AGENTS`` so REST order == in-process order."""
    if base_port is None:
        base_port = int(os.environ.get(PORT_ENV_VAR, BASE_PORT))

    names = [agent.name for agent in PIPELINE_AGENTS]
    services = []
    for index, name in enumerate(names):
        next_name = names[index + 1] if index + 1 < len(names) else SINK
        services.append(
            ServiceSpec(
                name=name,
                position=index + 1,
                host=host,
                port=base_port + index,
                next_name=next_name,
            )
        )
    return Topology(tuple(services))


def load_topology(source: str | Path | None = None) -> Topology:
    """Load a topology from JSON, from ``HW6_TOPOLOGY``, or fall back to the derived default."""
    source = source or os.environ.get(TOPOLOGY_ENV_VAR) or None
    if source is None:
        return default_topology()

    path = Path(source)
    payload = json.loads(path.read_text(encoding="utf-8"))
    services = []
    for index, entry in enumerate(payload.get("services", [])):
        services.append(
            ServiceSpec(
                name=str(entry["name"]),
                position=int(entry.get("position", index + 1)),
                host=str(entry.get("host", DEFAULT_HOST)),
                port=int(entry["port"]),
                next_name=str(entry.get("next", SINK)),
            )
        )
    return Topology(tuple(services))
