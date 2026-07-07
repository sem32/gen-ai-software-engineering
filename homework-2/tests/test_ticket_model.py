"""Validation tests driven through the API to exercise the model rules.

All validation failures should surface as HTTP 400 with the shape
``{"error": "Validation failed", "details": [{"field", "message"}]}``.
"""


def _post(client, payload):
    return client.post("/tickets", json=payload)


def test_missing_required_field_fails(client, valid_ticket):
    payload = valid_ticket()
    del payload["customer_email"]
    resp = _post(client, payload)
    assert resp.status_code == 400


def test_invalid_email_format_fails(client, valid_ticket):
    resp = _post(client, valid_ticket(customer_email="not-an-email"))
    assert resp.status_code == 400


def test_subject_min_length_ok(client, valid_ticket):
    resp = _post(client, valid_ticket(subject="a"))
    assert resp.status_code == 201


def test_subject_max_length_ok(client, valid_ticket):
    resp = _post(client, valid_ticket(subject="s" * 200))
    assert resp.status_code == 201


def test_subject_empty_fails(client, valid_ticket):
    resp = _post(client, valid_ticket(subject=""))
    assert resp.status_code == 400


def test_subject_too_long_fails(client, valid_ticket):
    resp = _post(client, valid_ticket(subject="s" * 201))
    assert resp.status_code == 400


def test_description_min_length_ok(client, valid_ticket):
    resp = _post(client, valid_ticket(description="0123456789"))  # exactly 10 chars
    assert resp.status_code == 201


def test_description_max_length_ok(client, valid_ticket):
    resp = _post(client, valid_ticket(description="d" * 2000))
    assert resp.status_code == 201


def test_description_too_short_fails(client, valid_ticket):
    resp = _post(client, valid_ticket(description="123456789"))  # 9 chars
    assert resp.status_code == 400


def test_invalid_category_fails(client, valid_ticket):
    resp = _post(client, valid_ticket(category="not_a_category"))
    assert resp.status_code == 400


def test_invalid_priority_fails(client, valid_ticket):
    resp = _post(client, valid_ticket(priority="superhigh"))
    assert resp.status_code == 400


def test_invalid_status_fails(client, valid_ticket):
    resp = _post(client, valid_ticket(status="archived"))
    assert resp.status_code == 400


def test_invalid_metadata_source_fails(client, valid_ticket):
    resp = _post(client, valid_ticket(metadata={"source": "carrier_pigeon"}))
    assert resp.status_code == 400


def test_invalid_metadata_device_type_fails(client, valid_ticket):
    resp = _post(client, valid_ticket(metadata={"device_type": "smartwatch"}))
    assert resp.status_code == 400


def test_validation_error_response_shape(client, valid_ticket):
    resp = _post(client, valid_ticket(subject=""))
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "Validation failed"
    assert isinstance(body["details"], list)
    assert body["details"]
    first = body["details"][0]
    assert "field" in first and "message" in first
