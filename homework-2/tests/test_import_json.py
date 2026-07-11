"""JSON bulk-import tests exercising POST /tickets/import for JSON payloads."""

from conftest import DEMO


def _upload(client, path, filename, query=""):
    with open(path, "rb") as fh:
        return client.post(
            f"/tickets/import{query}",
            files={"file": (filename, fh, "application/json")},
        )


def test_import_20_records_success(client):
    resp = _upload(client, DEMO / "sample_tickets.json", "sample_tickets.json", "?format=json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 20
    assert body["successful"] == 20
    assert body["failed"] == 0


def test_import_invalid_json_collects_errors(client):
    resp = _upload(client, DEMO / "sample_tickets_invalid.json", "sample_tickets_invalid.json", "?format=json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["failed"] >= 1
    assert body["errors"]
    assert "index" in body["errors"][0]


def test_import_malformed_json_returns_400(client):
    resp = _upload(client, DEMO / "malformed.json", "malformed.json", "?format=json")
    assert resp.status_code == 400
    assert resp.json()["error"] == "Import failed"


def test_import_format_inferred_from_extension(client):
    # No ?format query: the .json extension drives parser selection.
    resp = _upload(client, DEMO / "sample_tickets.json", "sample_tickets.json")
    assert resp.status_code == 200
    assert resp.json()["successful"] == 20


def test_import_undetectable_format_returns_400(client):
    # No ?format and an unrecognized extension: format cannot be determined.
    resp = client.post(
        "/tickets/import",
        files={"file": ("data.txt", b"whatever", "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "Import failed"


def test_import_unknown_format_query_returns_400(client):
    resp = client.post(
        "/tickets/import?format=yaml",
        files={"file": ("data.json", b"[]", "application/json")},
    )
    assert resp.status_code == 400


def test_import_format_query_overrides_extension(client):
    # Filename has a misleading .txt extension; ?format=json wins.
    resp = _upload(client, DEMO / "sample_tickets.json", "sample_tickets.txt", "?format=json")
    assert resp.status_code == 200
    assert resp.json()["successful"] == 20
