"""CSV bulk-import tests exercising POST /tickets/import?format=csv."""

from conftest import DEMO


def _upload(client, path, filename, query="?format=csv"):
    with open(path, "rb") as fh:
        return client.post(
            f"/tickets/import{query}",
            files={"file": (filename, fh, "text/csv")},
        )


def test_import_50_rows_success(client):
    resp = _upload(client, DEMO / "sample_tickets.csv", "sample_tickets.csv")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 50
    assert body["successful"] == 50
    assert body["failed"] == 0
    assert len(body["created_ids"]) == 50
    # Tickets are actually persisted.
    assert len(client.get("/tickets").json()) == 50


def test_import_invalid_csv_partial_success_with_errors(client):
    resp = _upload(client, DEMO / "sample_tickets_invalid.csv", "sample_tickets_invalid.csv")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["failed"] >= 1
    assert body["successful"] >= 1
    assert body["successful"] + body["failed"] == body["total"]
    # Each error entry carries an index and a list of field messages.
    assert body["errors"]
    first_error = body["errors"][0]
    assert "index" in first_error
    assert isinstance(first_error["errors"], list) and first_error["errors"]


def test_import_malformed_csv_missing_columns_returns_400(client):
    content = b"foo,bar\n1,2\n"
    resp = client.post(
        "/tickets/import?format=csv",
        files={"file": ("bad.csv", content, "text/csv")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "Import failed"


def test_import_csv_tags_parsed_to_list(client):
    _upload(client, DEMO / "sample_tickets.csv", "sample_tickets.csv")
    first = client.get("/tickets").json()[0]
    assert isinstance(first["tags"], list)
    assert first["tags"] == ["login", "password", "access"]


def test_import_csv_metadata_folded(client):
    _upload(client, DEMO / "sample_tickets.csv", "sample_tickets.csv")
    first = client.get("/tickets").json()[0]
    assert first["metadata"] == {
        "source": "web_form",
        "browser": "Chrome",
        "device_type": "desktop",
    }


def test_import_csv_with_auto_classify(client):
    resp = _upload(
        client,
        DEMO / "sample_tickets.csv",
        "sample_tickets.csv",
        query="?format=csv&auto_classify=true",
    )
    assert resp.status_code == 200
    first = client.get("/tickets").json()[0]
    assert first["classification"] is not None
    assert first["classification"]["category"] == first["category"]
