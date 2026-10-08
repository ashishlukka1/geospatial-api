"""Tests for feature extraction and the measurements endpoint.

Uses the shared throwaway database from conftest, so the real
PostgreSQL database is never touched.
"""

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from app.models import FeatureRecord
from app.services.features import to_json_safe

MIXED_KML = Path("sample_data/mixed.kml").read_bytes()


def upload_mixed_kml(client):
    """Upload the Polygon + LineString + Point sample file."""
    response = client.post("/api/files/", files={"file": ("mixed.kml", MIXED_KML)})
    assert response.status_code == 200
    return response.json()["id"]


def test_upload_mixed_kml_succeeds(client):
    """Test 1: a KML with Polygon, LineString and Point uploads cleanly."""
    file_id = upload_mixed_kml(client)
    body = client.get(f"/api/files/{file_id}/").json()
    assert body["status"] == "COMPLETED"


def test_feature_count_is_three(client):
    """Test 2: the file record reports exactly 3 features."""
    file_id = upload_mixed_kml(client)
    body = client.get(f"/api/files/{file_id}/").json()
    assert body["feature_count"] == 3


def test_geometry_types(client):
    """Test 3: stored features are Polygon, LineString and Point in order."""
    file_id = upload_mixed_kml(client)
    body = client.get(f"/api/files/{file_id}/measurements/").json()
    types = [item["geometry_type"] for item in body["features"]]
    assert types == ["Polygon", "LineString", "Point"]


def test_features_persisted_in_database(client, db_session):
    """Test 4: three rows exist in the features table for the file."""
    file_id = upload_mixed_kml(client)
    rows = (
        db_session.query(FeatureRecord)
        .filter(FeatureRecord.file_id == file_id)
        .order_by(FeatureRecord.feature_index)
        .all()
    )
    assert len(rows) == 3
    assert [row.feature_index for row in rows] == [0, 1, 2]
    assert rows[0].crs == "EPSG:4326"


def test_get_measurements_endpoint(client):
    """Test 5: GET measurements returns 200 with GeoJSON and null measurement."""
    file_id = upload_mixed_kml(client)
    response = client.get(f"/api/files/{file_id}/measurements/")
    assert response.status_code == 200
    body = response.json()
    assert body["file_id"] == file_id
    assert len(body["features"]) == 3
    first = body["features"][0]
    assert first["geometry"]["type"] == "Polygon"
    assert first["properties"]["Name"] == "Campus"
    assert all(item["measurement"] is None for item in body["features"])
    assert all(item["crs"] == "EPSG:4326" for item in body["features"])


def test_measurements_unknown_file_id_returns_404(client):
    """Test 6: measurements for an unknown ID returns HTTP 404."""
    response = client.get("/api/files/does-not-exist/measurements/")
    assert response.status_code == 404


def test_json_safe_conversion():
    """Test 7: NaN and NumPy values convert without serialization failures."""
    assert to_json_safe(float("nan")) is None
    assert to_json_safe(np.int64(3)) == 3
    assert to_json_safe(np.float64(2.5)) == 2.5
    assert to_json_safe(np.bool_(True)) is True
    assert to_json_safe(datetime(2024, 1, 2, 3, 4, 5)) == "2024-01-02T03:04:05"
    assert to_json_safe(pd.NA) is None
    nested = {"a": [float("nan"), np.int64(1)], "b": {"c": np.bool_(False)}}
    assert to_json_safe(nested) == {"a": [None, 1], "b": {"c": False}}
    json.dumps(to_json_safe(nested))


def test_missing_properties_serialize(client):
    """Test 7 (integration): the nameless Point returns null properties."""
    file_id = upload_mixed_kml(client)
    body = client.get(f"/api/files/{file_id}/measurements/").json()
    point = body["features"][2]
    assert point["geometry"]["type"] == "Point"
    assert point["properties"]["Name"] is None
