"""Tests for the REST gateway (spec task T-13, edge cases EC-22…EC-25).

Every test talks to a **real socket** on an ephemeral port, so the HTTP semantics — status codes,
headers, content types — are exercised rather than mocked, and a running demo can never collide with
the suite.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import SAMPLE_PATH
from gateway.errors import CATALOG, PROBLEM_CONTENT_TYPE, ApiProblem, problem_document
from gateway.server import MAX_BODY_BYTES, PipelineGateway, create_server
from gateway.validation import validate_submission

# --------------------------------------------------------------------------------------
# Fixtures and a tiny client
# --------------------------------------------------------------------------------------


@pytest.fixture
def server(tmp_path):
    gateway = PipelineGateway(tmp_path / "shared", SAMPLE_PATH)
    httpd = create_server(gateway, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


class Reply:
    def __init__(self, status, body, headers):
        self.status = status
        self.raw = body
        self.headers = headers

    @property
    def json(self):
        return json.loads(self.raw.decode("utf-8"))

    @property
    def text(self):
        return self.raw.decode("utf-8")


def call(base, path, method="GET", body=None, raw_body=None):
    data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return Reply(response.status, response.read(), response.headers)
    except urllib.error.HTTPError as exc:
        return Reply(exc.code, exc.read(), exc.headers)


def valid_transaction(**overrides):
    transaction = {
        "transaction_id": "HTTP001",
        "timestamp": "2026-03-16T09:00:00Z",
        "source_account": "ACC-1001",
        "destination_account": "ACC-2001",
        "amount": "1500.00",
        "currency": "USD",
        "transaction_type": "transfer",
        "description": "http submission",
        "metadata": {"channel": "api", "country": "US"},
    }
    transaction.update(overrides)
    return transaction


# --------------------------------------------------------------------------------------
# Surface
# --------------------------------------------------------------------------------------


def test_route_table_is_complete():
    paths = {(route.method, route.pattern.pattern) for route in PipelineGateway.ROUTES}
    assert ("GET", r"^/health$") in paths
    assert ("POST", r"^/transactions$") in paths
    assert ("POST", r"^/agents/(?P<agent_name>[a-z_]{1,64})/process$") in paths
    assert len(PipelineGateway.ROUTES) == len({(r.method, r.pattern.pattern) for r in PipelineGateway.ROUTES})


def test_health(server):
    reply = call(server, "/health")
    assert reply.status == 200
    payload = reply.json
    assert payload["status"] == "ok"
    assert payload["rule_pack"] == "policy-default"
    assert payload["pipeline_agents"][0] == "transaction_validator"
    assert "policy_engine" in payload["pipeline_agents"]
    assert reply.headers["X-Request-Id"]


def test_rules_endpoint_returns_the_pack(server):
    payload = call(server, "/rules").json
    assert payload["name"] == "policy-default"
    assert any(rule["id"] == "express_small_low_risk" for rule in payload["rules"])


def test_rules_endpoint_honours_the_override(server):
    assert call(server, "/rules?rules=policy-strict").json["name"] == "policy-strict"


def test_errors_endpoint_publishes_the_catalog(server):
    payload = call(server, "/errors").json
    assert payload["problem_format"] == "RFC 9457"
    codes = {entry["code"] for entry in payload["errors"]}
    assert codes == set(CATALOG)


def test_agents_endpoint_describes_the_chain(server):
    payload = call(server, "/agents").json
    assert payload["count"] == 5
    names = [agent["name"] for agent in payload["agents"]]
    assert names[0] == "transaction_validator"
    assert names[-1] == "settlement_processor"
    assert payload["agents"][0]["next_agent"] == "fraud_detector"


# --------------------------------------------------------------------------------------
# Submission — success and business verdicts
# --------------------------------------------------------------------------------------


def test_settled_submission_is_201_with_location(server):
    reply = call(server, "/transactions", "POST", valid_transaction())
    assert reply.status == 201
    assert reply.headers["Location"] == "/transactions/HTTP001"
    payload = reply.json
    assert payload["status"] == "settled"
    assert payload["net_amount"] == "1496.25"
    assert payload["rule_pack"] == "policy-default"


def test_ec_22_business_rejection_is_422_problem_json(server):
    reply = call(server, "/transactions", "POST", valid_transaction(transaction_id="BAD1", currency="XYZ"))
    assert reply.status == 422
    assert reply.headers["Content-Type"] == PROBLEM_CONTENT_TYPE
    payload = reply.json
    assert payload["code"] == "transaction_rejected"
    assert payload["type"] == "urn:hw6:error:transaction-rejected"
    assert payload["status"] == 422
    assert payload["instance"] == "/transactions"
    assert payload["request_id"]
    assert payload["reasons"] == ["unknown_currency:XYZ"]
    # The result is stored and retrievable — the 4xx is a verdict, not a lost request.
    assert reply.headers["Location"] == "/transactions/BAD1"
    assert call(server, "/transactions/BAD1").status == 200


def test_held_submission_is_409(server):
    reply = call(
        server, "/transactions", "POST", valid_transaction(transaction_id="HELD1", amount="75000.00")
    )
    assert reply.status == 409
    payload = reply.json
    assert payload["code"] == "transaction_held"
    assert payload["reasons"] == ["fraud_review_required"]
    assert payload["outcome"]["risk_score"] == 60


def test_rules_override_changes_one_submission_only(server):
    strict = call(
        server,
        "/transactions?rules=policy-strict",
        "POST",
        valid_transaction(transaction_id="STRICT1", amount="9999.99", metadata={"channel": "online", "country": "US"}),
    )
    assert strict.status == 409
    assert strict.json["reasons"] == ["structuring_manual_review"]

    default = call(
        server,
        "/transactions",
        "POST",
        valid_transaction(transaction_id="DEFAULT1", amount="9999.99", metadata={"channel": "online", "country": "US"}),
    )
    assert default.status == 201


# --------------------------------------------------------------------------------------
# Schema validation at the boundary (400)
# --------------------------------------------------------------------------------------


def test_validation_failure_is_400_with_field_errors(server):
    body = valid_transaction()
    del body["currency"]
    body["amount"] = 1500.0  # a JSON number, not a decimal string
    body["nope"] = 1

    reply = call(server, "/transactions", "POST", body)

    assert reply.status == 400
    payload = reply.json
    assert payload["code"] == "validation_failed"
    problems = {(item["field"], item["code"]) for item in payload["errors"]}
    assert ("currency", "missing_field") in problems
    assert ("amount", "wrong_type") in problems
    assert ("nope", "unknown_field") in problems


@pytest.mark.parametrize(
    "payload,expected_field",
    [
        ("not an object", "$"),
        ({"transaction_id": ""}, "transaction_id"),
        ({"metadata": "online"}, "metadata"),
    ],
)
def test_validate_submission_field_targets(payload, expected_field):
    errors = validate_submission(payload)
    assert any(error.field == expected_field for error in errors)


def test_metadata_values_must_be_scalars():
    errors = validate_submission(valid_transaction(metadata={"channel": {"nested": 1}}))
    assert any(error.field == "metadata.channel" for error in errors)


def test_overlong_string_is_rejected():
    errors = validate_submission(valid_transaction(description="x" * 300))
    assert any(error.code == "too_long" for error in errors)


def test_valid_transaction_has_no_schema_errors():
    assert validate_submission(valid_transaction()) == []


# --------------------------------------------------------------------------------------
# Request errors
# --------------------------------------------------------------------------------------


def test_ec_23_malformed_json(server):
    reply = call(server, "/transactions", "POST", raw_body=b"{oops")
    assert reply.status == 400
    assert reply.json["code"] == "invalid_json"
    assert reply.json["line"] == 1


def test_empty_body_is_rejected(server):
    reply = call(server, "/transactions", "POST", raw_body=b"")
    assert reply.status == 400
    assert reply.json["code"] == "invalid_body"


def test_ec_23_oversized_body(server):
    reply = call(server, "/transactions", "POST", raw_body=b"{" + b"x" * (MAX_BODY_BYTES + 10))
    assert reply.status == 413
    assert reply.json["code"] == "payload_too_large"
    assert reply.json["limit_bytes"] == MAX_BODY_BYTES
    # the server survives and keeps answering
    assert call(server, "/health").status == 200


def test_array_to_the_single_endpoint_is_rejected(server):
    reply = call(server, "/transactions", "POST", [valid_transaction()])
    assert reply.status == 400
    assert reply.json["code"] == "invalid_body"


def test_ec_25_unknown_transaction_and_wrong_method(server):
    missing = call(server, "/transactions/NOPE")
    assert missing.status == 404
    assert missing.json["code"] == "transaction_not_found"

    wrong = call(server, "/transactions", "DELETE")
    assert wrong.status == 405
    assert wrong.json["code"] == "method_not_allowed"
    assert "GET" in wrong.headers["Allow"] and "POST" in wrong.headers["Allow"]


def test_unknown_route_is_404(server):
    reply = call(server, "/nope")
    assert reply.status == 404
    assert reply.json["code"] == "not_found"


def test_options_advertises_methods(server):
    reply = call(server, "/health", "OPTIONS")
    assert reply.status == 204
    assert "GET" in reply.headers["Allow"]


@pytest.mark.parametrize(
    "path,code",
    [("/audit?limit=abc", "invalid_query"), ("/audit?limit=99999", "invalid_query"),
     ("/rules?rules=", "invalid_query"), ("/rules?rules=ghost", "invalid_query")],
)
def test_query_validation(server, path, code):
    reply = call(server, path)
    assert reply.status == 400
    assert reply.json["code"] == code


# --------------------------------------------------------------------------------------
# Batch
# --------------------------------------------------------------------------------------


def test_batch_all_settled_is_201(server):
    reply = call(
        server,
        "/transactions/batch",
        "POST",
        {"transactions": [valid_transaction(transaction_id="B1"), valid_transaction(transaction_id="B2")]},
    )
    assert reply.status == 201
    payload = reply.json
    assert payload["submitted"] == 2
    assert payload["by_status"] == {"settled": 2}


def test_batch_mixed_is_207_and_reports_each_item(server):
    reply = call(
        server,
        "/transactions/batch",
        "POST",
        [
            valid_transaction(transaction_id="M1"),
            valid_transaction(transaction_id="M2", currency="XYZ"),
            {"transaction_id": "M3"},
        ],
    )
    assert reply.status == 207
    items = reply.json["results"]
    assert [item["http_status"] for item in items] == [201, 422, 400]
    assert items[1]["problem"]["code"] == "transaction_rejected"
    assert items[2]["problem"]["code"] == "validation_failed"
    # one bad row must not discard the good one
    assert call(server, "/transactions/M1").json["status"] == "settled"


@pytest.mark.parametrize("body", [{"transactions": []}, {"transactions": "no"}, {}])
def test_batch_rejects_bad_shapes(server, body):
    assert call(server, "/transactions/batch", "POST", body).status == 400


def test_batch_size_limit(server):
    from gateway.server import MAX_BATCH

    reply = call(server, "/transactions/batch", "POST", [valid_transaction()] * (MAX_BATCH + 1))
    assert reply.status == 400
    assert "exceeds the limit" in reply.json["detail"]


# --------------------------------------------------------------------------------------
# Agent-as-a-service (CR-02)
# --------------------------------------------------------------------------------------


def test_single_agent_can_be_invoked(server):
    reply = call(server, "/agents/transaction_validator/process", "POST", valid_transaction())
    assert reply.status == 200
    payload = reply.json
    assert payload["agent"] == "transaction_validator"
    assert payload["status"] == "validated"
    assert payload["next_agent"] == "fraud_detector"
    assert payload["terminal"] is False


def test_agent_output_can_be_fed_to_the_next_agent(server):
    first = call(server, "/agents/transaction_validator/process", "POST", valid_transaction()).json
    second = call(server, "/agents/fraud_detector/process", "POST", first["message"]).json
    assert second["agent"] == "fraud_detector"
    assert second["message"]["data"]["fraud"]["risk_score"] == 0


def test_agent_rejects_a_message_addressed_elsewhere(server):
    first = call(server, "/agents/transaction_validator/process", "POST", valid_transaction()).json
    reply = call(server, "/agents/settlement_processor/process", "POST", first["message"])
    assert reply.status == 400
    assert reply.json["addressed_to"] == "fraud_detector"


def test_unknown_agent_is_404(server):
    reply = call(server, "/agents/ghost_agent/process", "POST", valid_transaction())
    assert reply.status == 404
    assert reply.json["code"] == "not_found"


def test_chain_walks_every_agent(server):
    payload = call(server, "/pipeline/chain", "POST", valid_transaction(transaction_id="CH1")).json
    assert payload["agents_invoked"] == 5
    assert payload["terminal"] is True
    assert payload["final_status"] == "settled"
    assert [hop["agent"] for hop in payload["hops"]][0] == "transaction_validator"


def test_chain_stops_early_on_a_terminal_verdict(server):
    payload = call(
        server, "/pipeline/chain", "POST", valid_transaction(transaction_id="CH2", currency="XYZ")
    ).json
    assert payload["agents_invoked"] == 1
    assert payload["final_status"] == "rejected"


def test_chain_writes_nothing(server):
    call(server, "/pipeline/chain", "POST", valid_transaction(transaction_id="CH3"))
    assert call(server, "/transactions/CH3").status == 404


# --------------------------------------------------------------------------------------
# Reads, concurrency, PII
# --------------------------------------------------------------------------------------


def test_sample_run_and_summaries(server):
    run = call(server, "/pipeline/run", "POST", {})
    assert run.status == 200
    assert run.json["by_status"] == {"held": 1, "rejected": 2, "settled": 5}

    listing = call(server, "/transactions").json
    assert listing["total"] == 8

    assert call(server, "/summary").json["total_transactions"] == 8
    markdown = call(server, "/summary.md")
    assert markdown.headers["Content-Type"].startswith("text/markdown")
    assert markdown.text.startswith("# Pipeline run summary")


def test_sample_run_under_the_strict_pack(server):
    run = call(server, "/pipeline/run?rules=policy-strict", "POST", {})
    assert run.json["by_status"] == {"held": 3, "rejected": 2, "settled": 3}


def test_audit_carries_the_request_id(server):
    call(server, "/transactions", "POST", valid_transaction(transaction_id="AUD1"))
    entries = call(server, "/audit?limit=500").json["entries"]
    gateway_entries = [entry for entry in entries if entry["agent"] == "pipeline-gateway"]
    assert gateway_entries
    assert all(entry["detail"]["request_id"] for entry in gateway_entries)


def test_ec_24_concurrent_submissions_each_land_once(server):
    def submit(index):
        return call(
            server,
            "/transactions",
            "POST",
            valid_transaction(transaction_id=f"CONC{index}", amount="100.00"),
        ).status

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(submit, range(10)))

    assert statuses == [201] * 10
    listing = call(server, "/transactions").json
    ids = [item["transaction_id"] for item in listing["transactions"] if item["transaction_id"].startswith("CONC")]
    assert len(ids) == 10 == len(set(ids))


def test_no_response_leaks_a_raw_account(server):
    call(server, "/pipeline/run", "POST", {})
    for path in ("/transactions", "/summary", "/audit?limit=500", "/health"):
        assert "ACC-" not in call(server, path).text, path

    submitted = call(server, "/transactions", "POST", valid_transaction(transaction_id="PII1"))
    assert "ACC-" not in submitted.text
    # Stronger than masking: the API projection carries no account field at all, so there is nothing
    # to leak even if the masking were to regress.
    assert "account" not in submitted.json


def test_stored_result_keeps_the_masked_form(server, tmp_path):
    """The account does exist on disk — masked — which is what the audit needs."""
    call(server, "/transactions", "POST", valid_transaction(transaction_id="PII2"))
    stored = list((tmp_path / "shared" / "results").glob("PII2-*.json"))
    assert stored, "the result file should have been written"
    content = stored[0].read_text(encoding="utf-8")
    assert "ACC-" not in content
    assert "****1001" in content
    assert '"description": "[redacted]"' in content


def test_agent_service_response_also_hides_accounts(server):
    """The stateless agent route returns an in-flight message — it must be masked from the validator on."""
    reply = call(server, "/agents/transaction_validator/process", "POST", valid_transaction())
    assert "ACC-" not in reply.text
    assert reply.json["message"]["data"]["source_account"] == "****1001"


# --------------------------------------------------------------------------------------
# The error module itself
# --------------------------------------------------------------------------------------


def test_every_catalog_entry_has_a_sane_status():
    for code, definition in CATALOG.items():
        assert 400 <= definition.status < 600, code
        assert definition.title
        assert definition.type_uri.startswith("urn:hw6:error:")
        assert definition.client_fault == (definition.status < 500)


def test_api_problem_rejects_an_unknown_code():
    with pytest.raises(ValueError, match="unknown error code"):
        ApiProblem("no_such_code", "nope")


def test_problem_document_shape():
    document = problem_document(
        "invalid_json", detail="bad", instance="/x", request_id="r1", extra="kept", dropped=None
    )
    assert document["type"] == "urn:hw6:error:invalid-json"
    assert document["status"] == 400
    assert document["code"] == "invalid_json"
    assert document["request_id"] == "r1"
    assert document["extra"] == "kept"
    assert "dropped" not in document


def test_retryable_problems_say_so():
    document = problem_document(
        "upstream_unavailable", detail="down", instance="/x", request_id="r"
    )
    assert document["retryable"] is True


def test_problem_from_exception_hides_unexpected_details():
    from gateway.errors import problem_from_exception

    problem = problem_from_exception(RuntimeError("path /secret/place failed"))
    assert problem.code == "pipeline_error"

    generic = problem_from_exception(ZeroDivisionError("division by zero"))
    assert generic.code == "internal_error"
    assert generic.detail == "internal error"
