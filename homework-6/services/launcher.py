"""Start the whole service mesh (CR-02, spec task T-18).

Two modes, on purpose:

* :func:`start_in_threads` — every service in this process on ephemeral ports. Real HTTP, real
  choreography, no subprocess overhead; this is what the tests use, so they cannot collide with a
  running demo.
* :func:`start_subprocesses` / ``python -m services`` — one OS process per agent, which is the shape
  ``demo.sh`` shows and the shape the architecture actually claims.

Both resolve the chicken-and-egg of choreography the same way: bind every socket first, learn the real
ports, *then* build the topology and hand each service its successor's URL.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from agents import PIPELINE_AGENTS  # noqa: E402
from agents.protocol import Workspace  # noqa: E402

from .agent_service import AgentService, AgentServiceHandler, create_service_server  # noqa: E402
from .client import wait_until_healthy  # noqa: E402
from .topology import SINK, DEFAULT_HOST, ServiceSpec, Topology  # noqa: E402


@dataclass
class RunningMesh:
    """Handles for a mesh started in threads."""

    topology: Topology
    servers: list
    threads: list[threading.Thread]
    services: dict[str, AgentService]

    @property
    def entrypoint(self) -> str:
        return self.topology.first.process_url

    def shutdown(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=5)


def free_port(host: str = DEFAULT_HOST) -> int:
    """Ask the OS for an unused port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return probe.getsockname()[1]


def start_in_threads(
    shared_root: Path | str, rules: str | None = None, host: str = DEFAULT_HOST
) -> RunningMesh:
    """Start every agent service in this process, each on its own ephemeral port."""
    names = [agent.name for agent in PIPELINE_AGENTS]
    workspace = Workspace.create(shared_root)

    # 1. bind first so the ports are real before anyone needs a successor URL
    bound: list[tuple[str, object]] = []
    for name in names:
        server = create_service_server(_Placeholder(name), host, 0)
        bound.append((name, server))

    # 2. now the topology is knowable
    specs = []
    for index, (name, server) in enumerate(bound):
        specs.append(
            ServiceSpec(
                name=name,
                position=index + 1,
                host=host,
                port=server.server_address[1],
                next_name=names[index + 1] if index + 1 < len(names) else SINK,
            )
        )
    topology = Topology(tuple(specs))

    # 3. give each handler its real service
    services: dict[str, AgentService] = {}
    threads: list[threading.Thread] = []
    servers = []
    for name, server in bound:
        service = AgentService(name, workspace, topology, rules)
        services[name] = service
        server.RequestHandlerClass.service = service  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, name=f"svc-{name}", daemon=True)
        thread.start()
        threads.append(thread)
        servers.append(server)

    for spec in topology.services:
        if not wait_until_healthy(spec.health_url, timeout=10.0):
            mesh = RunningMesh(topology, servers, threads, services)
            mesh.shutdown()
            raise RuntimeError(f"service {spec.name} did not become healthy")

    return RunningMesh(topology, servers, threads, services)


@contextmanager
def running_mesh(
    shared_root: Path | str, rules: str | None = None
) -> Iterator[RunningMesh]:
    """Context manager form — guarantees shutdown even when the body raises."""
    mesh = start_in_threads(shared_root, rules)
    try:
        yield mesh
    finally:
        mesh.shutdown()


class _Placeholder:
    """Stands in for an :class:`AgentService` between binding and wiring."""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    def health(self) -> dict[str, str]:  # pragma: no cover - never served
        return {"status": "starting", "agent": self.agent_name}


def _assert_ports_free(topology: Topology, host: str = DEFAULT_HOST) -> None:
    """Refuse to start on an occupied port.

    A contiguous block from a base port is convenient but not reservable: something else may already
    hold one of them. Better to say which port and stop than to leave half a mesh running and blame
    the choreography later.
    """
    for spec in topology.services:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, spec.port))
            except OSError as exc:
                raise RuntimeError(
                    f"port {spec.port} (wanted by {spec.name}) is already in use: {exc.strerror}. "
                    f"Pass --base-port with a free block of {len(topology.services)} ports."
                ) from exc


def start_subprocesses(
    shared_root: Path | str,
    rules: str | None = None,
    host: str = DEFAULT_HOST,
    base_port: int | None = None,
) -> tuple[Topology, list[subprocess.Popen]]:
    """Start one OS process per agent — the shape ``demo.sh`` demonstrates."""
    from .topology import PORT_ENV_VAR, default_topology

    topology = default_topology(host, base_port)
    _assert_ports_free(topology)
    python = sys.executable
    processes: list[subprocess.Popen] = []

    # Every child must compute the SAME topology as the parent, or it will forward to the default
    # port block instead of the one actually in use — and only the first hop would ever work.
    child_env = {**os.environ, PORT_ENV_VAR: str(topology.first.port)}

    for spec in topology.services:
        command = [
            python,
            "-m",
            "services.agent_service",
            "--agent",
            spec.name,
            "--shared",
            str(shared_root),
            "--host",
            spec.host,
            "--port",
            str(spec.port),
        ]
        if rules:
            command += ["--rules", rules]
        processes.append(subprocess.Popen(command, cwd=PROJECT_ROOT, env=child_env))

    for spec in topology.services:
        if not wait_until_healthy(spec.health_url, timeout=20.0):
            for process in processes:
                process.terminate()
            raise RuntimeError(f"service {spec.name} did not become healthy on {spec.port}")

    return topology, processes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start every pipeline agent as an HTTP service")
    parser.add_argument("--shared", default=str(PROJECT_ROOT / "shared"))
    parser.add_argument("--rules", default=None)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--base-port", type=int, default=None)
    parser.add_argument(
        "--print-topology", action="store_true", help="print the topology JSON and exit"
    )
    args = parser.parse_args(argv)

    if args.print_topology:
        from .topology import default_topology

        print(default_topology(args.host, args.base_port).to_json())
        return 0

    topology, processes = start_subprocesses(args.shared, args.rules, args.host, args.base_port)
    print("service mesh up:", flush=True)
    for spec in topology.services:
        print(f"  {spec.position}. {spec.name:<24} {spec.base_url}  -> {spec.next_name}", flush=True)
    print(f"entrypoint: {topology.first.process_url}", flush=True)

    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\nstopping service mesh", flush=True)
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover
                process.kill()
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
