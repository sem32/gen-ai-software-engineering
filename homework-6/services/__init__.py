"""Agent microservices (CR-02): each pipeline agent as an independent REST service.

The services talk to each other over HTTP (choreography, not orchestration); the file journal under
``shared/audit`` and ``shared/results`` remains for logging and terminal results.
"""

from __future__ import annotations

from .agent_service import AgentService, create_service_server
from .client import TransportError, get_json, post_json, wait_until_healthy
from .launcher import RunningMesh, running_mesh, start_in_threads, start_subprocesses
from .topology import SINK, ServiceSpec, Topology, default_topology, load_topology

__all__ = [
    "AgentService",
    "RunningMesh",
    "SINK",
    "ServiceSpec",
    "Topology",
    "TransportError",
    "create_service_server",
    "default_topology",
    "get_json",
    "load_topology",
    "post_json",
    "running_mesh",
    "start_in_threads",
    "start_subprocesses",
    "wait_until_healthy",
]
