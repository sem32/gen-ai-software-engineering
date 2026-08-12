"""Tests for the agent microservice mesh (CR-02, spec tasks T-17/T-18, edge cases EC-27…EC-32).

The mesh runs in threads on ephemeral ports: real HTTP, real service-to-service choreography, no
subprocesses and no fixed ports, so these tests cannot collide with a running ``demo.sh``.
"""

from __future__ import annotations

import json

import pytest

from agents.protocol import build_message
from conftest import SAMPLE_PATH
from services.client import TransportError, get_json, post_json, wait_until_healthy
from services.launcher import free_port, running_mesh, start_in_threads
from services.topology import SINK, ServiceSpec, Topology, default_topology, load_topology


@pytest.fixture(scope="module")
def mesh(tmp_path_factory):
    shared = tmp_path_factory.mktemp("mesh") / "shared"
    with running_mesh(shared) as running:
        yield running


@pytest.fixture(scope="module")
def sample():
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def submit(mesh, transaction):
    message = build_message("api_client", "transaction_validator", "transaction", transaction)
    return post_json(mesh.entrypoint, message)


def raw_post(url, payload):
    """POST once and return ``(status, body)`` whatever the status.

    :func:`services.client.post_json` deliberately retries and then *raises* on 5xx, because that is
    what a service hop should do. A test that wants to read the 503 document needs the unfiltered
    exchange, so it makes it here rather than weakening the client.
    """
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def transaction(transaction_id, **overrides):
    payload = {
        "transaction_id": transaction_id,
        "timestamp": "2026-03-16T09:00:00Z",
        "source_account": "ACC-1001",
        "destination_account": "ACC-2001",
        "amount": "1500.00",
        "currency": "USD",
        "transaction_type": "transfer",
        "metadata": {"channel": "api", "country": "US"},
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------------------
# Topology
# --------------------------------------------------------------------------------------


def test_default_topology_mirrors_the_pipeline_order():
    from agents import PIPELINE_AGENTS

    topology = default_topology()
    assert [service.name for service in topology.services] == [a.name for a in PIPELINE_AGENTS]
    assert topology.services[-1].next_name == SINK
    assert topology.services[-1].is_terminal_hop
    assert topology.first.name == "transaction_validator"


def test_next_url_of_walks_the_chain():
    topology = default_topology()
    assert topology.next_url_of("transaction_validator").endswith("/process")
    assert topology.next_url_of("settlement_processor") is None


def test_unknown_service_is_named_in_the_error():
    with pytest.raises(KeyError, match="unknown service"):
        default_topology().get("ghost")


def test_topology_needs_at_least_one_service():
    with pytest.raises(ValueError, match="at least one service"):
        Topology(())


def test_topology_round_trips_through_json(tmp_path):
    path = tmp_path / "topology.json"
    path.write_text(default_topology().to_json(), encoding="utf-8")
    loaded = load_topology(path)
    assert [s.name for s in loaded.services] == [s.name for s in default_topology().services]


def test_topology_env_var_is_honoured(tmp_path, monkeypatch):
    path = tmp_path / "t.json"
    payload = {
        "services": [{"name": "transaction_validator", "port": 9999, "next": SINK}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("HW6_TOPOLOGY", str(path))
    assert load_topology().first.port == 9999


def test_base_port_env_var_shifts_every_port(monkeypatch):
    monkeypatch.setenv("HW6_SERVICE_BASE_PORT", "9100")
    assert default_topology().first.port == 9100


def test_service_spec_urls():
    spec = ServiceSpec("a", 1, "127.0.0.1", 8000, "b")
    assert spec.base_url == "http://127.0.0.1:8000"
    assert spec.process_url == "http://127.0.0.1:8000/process"
    assert spec.health_url == "http://127.0.0.1:8000/health"
    assert spec.as_dict()["next"] == "b"


def test_free_port_is_usable():
    assert 1024 < free_port() < 65536


# --------------------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------------------


def test_every_service_is_healthy_and_knows_its_successor(mesh):
    for spec in mesh.topology.services:
        payload = get_json(spec.health_url).payload
        assert payload["status"] == "ok"
        assert payload["agent"] == spec.name
        assert payload["inbox_transport"] == "rest"
        assert payload["next"] == spec.next_name
        if spec.is_terminal_hop:
            assert payload["next_url"] is None
        else:
            assert payload["next_url"].endswith("/process")


def test_policy_service_reports_its_rule_pack(mesh):
    health = get_json(mesh.topology.get("policy_engine").health_url).payload
    assert health["rule_pack"] == "policy-default"


def test_unknown_route_on_a_service_is_404(mesh):
    reply = get_json(mesh.topology.first.base_url + "/nope")
    assert reply.status == 404
    assert reply.payload["code"] == "not_found"


# --------------------------------------------------------------------------------------
# Choreography: §8 over REST
# --------------------------------------------------------------------------------------

EXPECTED = {
    "TXN001": (200, "settled", 5),
    "TXN002": (200, "settled", 5),
    "TXN003": (200, "settled", 5),
    "TXN004": (200, "settled", 5),
    "TXN005": (409, "held", 3),
    "TXN006": (422, "rejected", 1),
    "TXN007": (422, "rejected", 1),
    "TXN008": (200, "settled", 5),
}


@pytest.fixture(scope="module")
def rest_results(mesh, sample):
    return {txn["transaction_id"]: submit(mesh, txn) for txn in sample}


@pytest.mark.parametrize("transaction_id", sorted(EXPECTED))
def test_rest_chain_reproduces_section_8(rest_results, transaction_id):
    expected_status, expected_verdict, expected_hops = EXPECTED[transaction_id]
    reply = rest_results[transaction_id]

    assert reply.status == expected_status
    body = reply.payload
    assert len(body["trace"]) == expected_hops
    outcome = body.get("outcome")
    assert outcome["status"] == expected_verdict


def test_trace_reads_first_to_last(rest_results):
    trace = rest_results["TXN001"]["trace"] if isinstance(rest_results["TXN001"], dict) else rest_results["TXN001"].payload["trace"]
    assert [hop["agent"] for hop in trace] == [
        "transaction_validator",
        "fraud_detector",
        "compliance_checker",
        "policy_engine",
        "settlement_processor",
    ]
    assert [hop["position"] for hop in trace] == [1, 2, 3, 4, 5]
    assert trace[-1]["terminal"] is True


def test_a_rejected_transaction_never_reaches_the_second_service(rest_results):
    trace = rest_results["TXN006"].payload["trace"]
    assert [hop["agent"] for hop in trace] == ["transaction_validator"]


def test_terminal_results_are_written_to_the_file_journal(mesh, rest_results):
    """CR-02 keeps files for logging: the terminal hop still writes the result."""
    results = list((mesh.services["settlement_processor"].workspace.results_dir).glob("*.json"))
    assert len(results) == 8


def test_every_hop_is_in_the_audit_journal(mesh, rest_results):
    entries = mesh.services["transaction_validator"].audit.entries()
    rest_entries = [e for e in entries if (e["detail"] or {}).get("transport") == "rest"]
    assert rest_entries
    agents_seen = {entry["agent"] for entry in rest_entries}
    assert agents_seen == {
        "transaction_validator",
        "fraud_detector",
        "compliance_checker",
        "policy_engine",
        "settlement_processor",
    }
    assert all(entry["detail"]["request_id"] for entry in rest_entries)


def test_audit_journal_never_contains_a_raw_account(mesh, rest_results):
    raw = mesh.services["transaction_validator"].audit.log_path.read_text(encoding="utf-8")
    assert "ACC-" not in raw


# --------------------------------------------------------------------------------------
# Idempotency (EC-28)
# --------------------------------------------------------------------------------------


def test_ec_28_replaying_a_message_id_does_not_double_process(mesh):
    transaction = {
        "transaction_id": "IDEM1",
        "timestamp": "2026-03-16T09:00:00Z",
        "source_account": "ACC-1001",
        "destination_account": "ACC-2001",
        "amount": "1500.00",
        "currency": "USD",
        "transaction_type": "transfer",
        "metadata": {"channel": "api", "country": "US"},
    }
    message = build_message("api_client", "transaction_validator", "transaction", transaction)

    first = post_json(mesh.entrypoint, message)
    second = post_json(mesh.entrypoint, message)

    assert first.status == second.status == 200
    assert second.payload["idempotent_replay"] is True
    assert "idempotent_replay" not in first.payload
    # exactly one result file, not two
    written = list(mesh.services["settlement_processor"].workspace.results_dir.glob("IDEM1-*.json"))
    assert len(written) == 1


# --------------------------------------------------------------------------------------
# Error propagation and transport faults
# --------------------------------------------------------------------------------------


def test_ec_29_message_addressed_to_the_wrong_service_is_400(mesh):
    message = build_message("api_client", "fraud_detector", "transaction", {"transaction_id": "X"})
    reply = post_json(mesh.topology.first.process_url, message)
    assert reply.status == 400
    assert reply.payload["code"] == "invalid_body"
    assert reply.payload["addressed_to"] == "fraud_detector"


def test_a_non_message_body_is_rejected(mesh):
    reply = post_json(mesh.entrypoint, {"not": "a message"})
    assert reply.status == 400
    assert reply.payload["code"] in ("invalid_body", "validation_failed")


def test_garbage_payload_is_a_validation_error_not_a_500(mesh):
    message = build_message("api_client", "transaction_validator", "transaction", {})
    reply = post_json(mesh.entrypoint, message)
    # an empty payload is business-invalid, so the validator rejects it: a verdict, not a crash
    assert reply.status == 422
    assert reply.payload["code"] == "transaction_rejected"


def _mesh_with_fraud_detector_down(shared):
    """Start a mesh, then stop the second service so the first hop has nowhere to forward."""
    mesh = start_in_threads(shared)
    index = [service.name for service in mesh.topology.services].index("fraud_detector")
    mesh.servers[index].shutdown()
    mesh.servers[index].server_close()
    return mesh, index


def _shutdown_except(mesh, skip_index):
    for position, server in enumerate(mesh.servers):
        if position != skip_index:
            server.shutdown()
            server.server_close()


def test_ec_30_unreachable_successor_is_503_and_retryable(tmp_path):
    """The first hop must fail loudly rather than swallow the message."""
    mesh, down = _mesh_with_fraud_detector_down(tmp_path / "shared")
    try:
        message = build_message(
            "api_client", "transaction_validator", "transaction", transaction("DOWN1")
        )
        status, body = raw_post(mesh.entrypoint, message)

        assert status == 503
        assert body["code"] == "upstream_unavailable"
        assert body["retryable"] is True
        assert body["next_agent"] == "fraud_detector"
        assert body["attempts"] >= 1
        assert "127.0.0.1" not in json.dumps(body)  # no internal URL leaks to the caller
    finally:
        _shutdown_except(mesh, down)


def test_client_retries_a_transport_fault_then_gives_up(tmp_path):
    """From a caller's point of view a 5xx chain is a transport fault, and the client raises."""
    mesh, down = _mesh_with_fraud_detector_down(tmp_path / "shared")
    try:
        message = build_message(
            "api_client", "transaction_validator", "transaction", transaction("DOWN3")
        )
        with pytest.raises(TransportError, match="failed after 2 attempt"):
            post_json(mesh.entrypoint, message, retries=1, backoff=0)
    finally:
        _shutdown_except(mesh, down)


def test_forward_failure_is_recorded_in_the_journal(tmp_path):
    mesh, down = _mesh_with_fraud_detector_down(tmp_path / "shared")
    try:
        message = build_message(
            "api_client", "transaction_validator", "transaction", transaction("DOWN2")
        )
        raw_post(mesh.entrypoint, message)
        outcomes = [
            entry["outcome"] for entry in mesh.services["transaction_validator"].audit.entries()
        ]
        assert "forward_failed" in outcomes
    finally:
        _shutdown_except(mesh, down)


# --------------------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------------------


def test_client_raises_transport_error_on_a_closed_port():
    port = free_port()
    with pytest.raises(TransportError, match="failed after"):
        post_json(f"http://127.0.0.1:{port}/process", {}, retries=0, backoff=0)


def test_wait_until_healthy_gives_up(monkeypatch):
    port = free_port()
    assert wait_until_healthy(f"http://127.0.0.1:{port}/health", timeout=0.3, interval=0.05) is False


def test_wait_until_healthy_succeeds_for_a_live_service(mesh):
    assert wait_until_healthy(mesh.topology.first.health_url, timeout=5.0) is True


def test_get_json_on_a_closed_port_raises():
    with pytest.raises(TransportError):
        get_json(f"http://127.0.0.1:{free_port()}/health", timeout=0.5)


def test_client_does_not_retry_a_business_verdict(mesh):
    """A 4xx is an answer. Retrying it would multiply load for no possible change."""
    message = build_message(
        "api_client",
        "transaction_validator",
        "transaction",
        {
            "transaction_id": "NORETRY",
            "timestamp": "2026-03-16T09:00:00Z",
            "source_account": "ACC-1001",
            "destination_account": "ACC-2001",
            "amount": "200.00",
            "currency": "XYZ",
            "transaction_type": "transfer",
            "metadata": {"channel": "api", "country": "US"},
        },
    )
    reply = post_json(mesh.entrypoint, message, retries=5)
    assert reply.status == 422
    assert reply.is_client_error


# --------------------------------------------------------------------------------------
# Both transports agree (CR-02.3)
# --------------------------------------------------------------------------------------


def test_rest_and_inprocess_transports_agree(rest_results, tmp_path):
    """The whole point of keeping two transports: they must never disagree on a verdict."""
    from integrator import run_pipeline

    summary = run_pipeline(SAMPLE_PATH, tmp_path / "inprocess", verbose=False)
    inprocess = {row["transaction_id"]: row["status"] for row in summary["transactions"]}

    over_rest = {
        transaction_id: reply.payload["outcome"]["status"]
        for transaction_id, reply in rest_results.items()
    }
    assert over_rest == inprocess
