"""XML bulk-import tests exercising POST /tickets/import for XML payloads."""

from pathlib import Path

from conftest import DEMO

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _upload(client, path, filename, query=""):
    with open(path, "rb") as fh:
        return client.post(
            f"/tickets/import{query}",
            files={"file": (filename, fh, "application/xml")},
        )


def test_import_30_tickets_success(client):
    resp = _upload(client, DEMO / "sample_tickets.xml", "sample_tickets.xml", "?format=xml")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 30
    assert body["successful"] == 30
    assert body["failed"] == 0


def test_import_xml_tags_and_metadata_parsed(client):
    _upload(client, DEMO / "sample_tickets.xml", "sample_tickets.xml", "?format=xml")
    first = client.get("/tickets").json()[0]
    assert first["tags"] == ["login", "password", "authentication"]
    assert first["metadata"] == {
        "source": "web_form",
        "browser": "Chrome",
        "device_type": "desktop",
    }


def test_import_malformed_xml_returns_400(client):
    resp = _upload(client, DEMO / "malformed.xml", "malformed.xml", "?format=xml")
    assert resp.status_code == 400
    assert resp.json()["error"] == "Import failed"


def test_import_xml_per_record_validation_error(client):
    resp = _upload(client, FIXTURES / "invalid_records.xml", "invalid_records.xml", "?format=xml")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["successful"] == 1
    assert body["failed"] == 1
    assert body["errors"][0]["index"] == 1


def test_import_empty_xml_edge_case(client):
    resp = _upload(client, FIXTURES / "empty.xml", "empty.xml", "?format=xml")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["successful"] == 0
    assert body["failed"] == 0
    assert body["created_ids"] == []
