"""Tests for Iteration 4 zipped-Shapefile support. Uses shared test DB."""

import io
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Polygon

from app.services import shapefile as shp_service


def _sample_gdf(crs="EPSG:4326"):
    """Two small polygons near Bangalore (shapefiles are single-type)."""
    poly1 = Polygon(
        [(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98)]
    )
    poly2 = Polygon(
        [(77.61, 12.99), (77.62, 12.99), (77.62, 13.00), (77.61, 13.00)]
    )
    return gpd.GeoDataFrame(
        {"name": ["a", "b"]}, geometry=[poly1, poly2], crs=crs
    )


def _line_gdf(crs="EPSG:4326"):
    line = LineString([(77.59, 12.97), (77.60, 12.98)])
    return gpd.GeoDataFrame({"name": ["line"]}, geometry=[line], crs=crs)


def _write_shapefile(gdf, directory: Path, name="layer"):
    shp_path = directory / f"{name}.shp"
    gdf.to_file(shp_path)
    return directory


def _write_gdf_zip(gdf, tmp_path: Path, name="valid", arc_prefix=""):
    work = tmp_path / f"work_{name}"
    if work.exists():
        import shutil
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    _write_shapefile(gdf, work)
    dest = tmp_path / f"{name}.zip"
    return _zip_dir(work, dest, arc_prefix)


def _zip_dir(source_dir: Path, dest_zip: Path, arc_prefix=""):
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in source_dir.rglob("*"):
            if path.is_file():
                arc = (Path(arc_prefix) / path.relative_to(source_dir)).as_posix()
                zf.write(path, arc)
    return dest_zip.read_bytes()


def make_valid_zip_bytes(tmp_path, nested=False, crs="EPSG:4326"):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    _write_shapefile(_sample_gdf(crs), work)
    dest = tmp_path / "valid.zip"
    prefix = "nested/inner" if nested else ""
    return _zip_dir(work, dest, prefix)


def upload_zip(client, data: bytes, filename="layer.zip"):
    return client.post("/api/files/", files={"file": (filename, data, "application/zip")})


# --- Successful processing ---

def test_valid_zip_at_root(client, tmp_path):
    data = make_valid_zip_bytes(tmp_path)
    res = upload_zip(client, data)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 2
    assert body["crs"] == "EPSG:4326"


def test_valid_zip_nested_dir(client, tmp_path):
    data = make_valid_zip_bytes(tmp_path, nested=True)
    res = upload_zip(client, data)
    assert res.status_code == 200, res.text
    assert res.json()["feature_count"] == 2


def test_shapefile_measurements_and_crs(client, tmp_path):
    data = make_valid_zip_bytes(tmp_path)
    file_id = upload_zip(client, data).json()["id"]
    meas = client.get(f"/api/files/{file_id}/measurements/").json()
    assert len(meas["features"]) == 2
    poly = meas["features"][0]
    assert poly["geometry_type"] == "Polygon"
    assert poly["measurement"]["type"] == "area"
    assert poly["measurement"]["value"] > 0
    assert poly["measurement"]["unit"] == "m²"
    assert all(f["crs"] == "EPSG:4326" for f in meas["features"])
    assert poly["projected_crs"] == "EPSG:32643"  # UTM zone 43N for 77.6E
    assert poly["geometry"]["type"] == "Polygon"


def test_linestring_length(client, tmp_path):
    data = _write_gdf_zip(_line_gdf(), tmp_path, name="line")
    file_id = upload_zip(client, data).json()["id"]
    meas = client.get(f"/api/files/{file_id}/measurements/").json()
    assert meas["features"][0]["geometry_type"] == "LineString"
    assert meas["features"][0]["measurement"]["type"] == "length"
    assert meas["features"][0]["measurement"]["value"] > 0


def test_projected_source_crs_preserved(client, tmp_path):
    gdf_utm = _sample_gdf("EPSG:4326").to_crs("EPSG:32643")
    work = tmp_path / "utm"
    work.mkdir(exist_ok=True)
    _write_shapefile(gdf_utm, work)
    dest = tmp_path / "utm.zip"
    data = _zip_dir(work, dest)
    file_id = upload_zip(client, data).json()["id"]
    info = client.get(f"/api/files/{file_id}/").json()
    assert info["crs"] == "EPSG:32643"
    meas = client.get(f"/api/files/{file_id}/measurements/").json()
    assert meas["features"][0]["crs"] == "EPSG:32643"
    assert meas["features"][0]["measurement"]["type"] == "area"
    assert meas["features"][0]["measurement"]["value"] > 0


# --- Failure handling ---

def test_renamed_text_as_zip_rejected(client):
    res = upload_zip(client, b"hello, this is not a zip")
    assert res.status_code == 400


def test_corrupt_zip_rejected(client):
    res = upload_zip(client, b"PK\x03\x04corrupt!!\x00\xff\xab" * 10)
    assert res.status_code == 400


def test_no_shp_rejected(client, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no shapefile here")
    res = upload_zip(client, buf.getvalue())
    assert res.status_code == 400
    assert ".shp" in res.json()["detail"]


def test_missing_companion_rejected(client, tmp_path):
    work = tmp_path / "incomplete"
    work.mkdir(exist_ok=True)
    _write_shapefile(_sample_gdf(), work)
    # Zip only .shp + .prj, omit .dbf.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for ext in (".shp", ".shx", ".prj"):
            cand = work / f"layer{ext}"
            if cand.exists():
                zf.write(cand, cand.name)
    res = upload_zip(client, buf.getvalue())
    assert res.status_code == 400
    assert ".dbf" in res.json()["detail"]


def test_multiple_shp_rejected(client, tmp_path):
    work = tmp_path / "multi"
    work.mkdir(exist_ok=True)
    _write_shapefile(_sample_gdf(), work, name="a")
    _write_shapefile(_sample_gdf(), work, name="b")
    dest = tmp_path / "multi.zip"
    data = _zip_dir(work, dest)
    res = upload_zip(client, data)
    assert res.status_code == 400
    assert "exactly one" in res.json()["detail"]


def test_missing_crs_rejected(client, tmp_path):
    gdf = _sample_gdf()
    gdf.crs = None
    work = tmp_path / "nocrs"
    work.mkdir(exist_ok=True)
    gdf.to_file(work / "layer.shp")
    dest = tmp_path / "nocrs.zip"
    data = _zip_dir(work, dest)
    res = upload_zip(client, data)
    assert res.status_code == 400
    assert "CRS" in res.json()["detail"]


def test_path_traversal_rejected(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "traversal")
        zf.writestr("layer.shp", "fake")
    res = upload_zip(client, buf.getvalue())
    assert res.status_code == 400
    assert "Unsafe" in res.json()["detail"]


def test_absolute_path_rejected(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("/tmp/evil.txt", "absolute")
    res = upload_zip(client, buf.getvalue())
    assert res.status_code == 400


def test_oversized_archive_rejected(client, tmp_path, monkeypatch):
    monkeypatch.setattr(shp_service, "MAX_UNCOMPRESSED_SIZE", 100)
    data = make_valid_zip_bytes(tmp_path)
    res = upload_zip(client, data)
    assert res.status_code == 413
    assert "limit" in res.json()["detail"].lower()


def test_temp_dir_cleaned_up(client, tmp_path):
    before = set(Path(tempfile.gettempdir()).iterdir())
    data = make_valid_zip_bytes(tmp_path)
    assert upload_zip(client, data).status_code == 200
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no shp")
    assert upload_zip(client, buf.getvalue()).status_code == 400
    after = set(Path(tempfile.gettempdir()).iterdir())
    leftover = [p for p in (after - before) if p.name.startswith("shp_")]
    assert leftover == []
