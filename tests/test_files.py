"""Tests for KML upload and file information endpoints.

Uses the shared throwaway database from conftest, so the real
PostgreSQL database is never touched.
"""

from pathlib import Path

from app.models import FileRecord

SAMPLE_KML = Path("sample_data/sample.kml").read_bytes()


def test_upload_valid_kml(client):
    """A valid KML upload returns COMPLETED with 2 features."""
    response = client.post("/api/files/", files={"file": ("sample.kml", SAMPLE_KML)})
    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "sample.kml"
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 2
    assert body["crs"] == "EPSG:4326"


def test_upload_invalid_extension(client):
    """A non-KML file is rejected with HTTP 400."""
    response = client.post("/api/files/", files={"file": ("notes.txt", b"hello")})
    assert response.status_code == 400


def test_upload_empty_file(client):
    """An empty KML file is rejected with HTTP 400."""
    response = client.post("/api/files/", files={"file": ("empty.kml", b"")})
    assert response.status_code == 400


def test_get_file_info_success(client):
    """Uploading then fetching by ID returns the same record."""
    upload = client.post("/api/files/", files={"file": ("sample.kml", SAMPLE_KML)})
    file_id = upload.json()["id"]
    response = client.get(f"/api/files/{file_id}/")
    assert response.status_code == 200
    assert response.json()["id"] == file_id


def test_get_unknown_file_id_returns_404(client):
    """Fetching an ID that was never uploaded returns HTTP 404."""
    response = client.get("/api/files/does-not-exist/")
    assert response.status_code == 404


def test_database_record_created_after_upload(client, db_session):
    """A successful upload leaves a COMPLETED row in the database."""
    upload = client.post("/api/files/", files={"file": ("sample.kml", SAMPLE_KML)})
    file_id = upload.json()["id"]
    record = db_session.get(FileRecord, file_id)
    assert record is not None
    assert record.status == "COMPLETED"
    assert record.feature_count == 2
