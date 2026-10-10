"""Iteration 5 robustness regression tests. Shared test DB only.

Uses only the `client` / `db_session` fixtures (never a raw session:
the in-memory SQLite connection is shared, and extra sessions break
later tests' visibility).
"""

import io
import math
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon
from sqlalchemy.orm import Session

from app.models import FeatureRecord, FileRecord
from app.services import file_handler as fh_service
from app.services import validate as validate_service
from app.services.features import to_json_safe

SAMPLE_KML = Path("sample_data/sample.kml").read_bytes()


def _poly(x0=77.59, y0=12.97, size=0.01):
    return Polygon(
        [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)]
    )


def _poly_gdf(crs="EPSG:4326"):
    return gpd.GeoDataFrame({"name": ["a"]}, geometry=[_poly()], crs=crs)


def _write_shp(gdf, directory: Path, name="layer"):
    directory.mkdir(parents=True, exist_ok=True)
    gdf.to_file(directory / f"{name}.shp")


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in entries.items():
            zf.writestr(arcname, data)
    return buf.getvalue()


def _shp_entries(work: Path) -> dict[str, bytes]:
    return {
        p.name: p.read_bytes() for p in work.iterdir() if p.is_file()
    }


def _upload(client, filename, data: bytes):
    return client.post("/api/files/", files={"file": (filename, data)})


def _valid_layer_zip(tmp_path, dirname="ok") -> bytes:
    work = tmp_path / dirname
    _write_shp(_poly_gdf(), work)
    return _zip_bytes({f"layer/{k}": v for k, v in _shp_entries(work).items()})


NAN_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>nan</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
77.59,12.97,0 NaN,12.98,0 77.60,12.97,0 77.59,12.97,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
</Document></kml>""".encode()

MULTI_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>multi</name><MultiGeometry>
<Polygon><outerBoundaryIs><LinearRing><coordinates>77.59,12.97,0 77.60,12.97,0 77.60,12.98,0 77.59,12.97,0</coordinates></LinearRing></outerBoundaryIs></Polygon>
<Point><coordinates>77.59,12.97,0</coordinates></Point>
</MultiGeometry></Placemark>
</Document></kml>""".encode()

NOGEOM_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>nodesc</name><description>no geometry here</description></Placemark>
</Document></kml>""".encode()

MIXED_NULL_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>poly</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
77.59,12.97,0 77.60,12.97,0 77.60,12.98,0 77.59,12.97,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>nodesc</name><description>no geometry here</description></Placemark>
</Document></kml>""".encode()

EMPTY_DOC_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>empty</name></Document></kml>""".encode()


# ---------- Upload and ZIP validation ----------

def test_empty_zip_rejected(client):
    res = _upload(client, "empty.zip", b"")
    assert res.status_code == 400


def test_unsupported_extension_rejected(client):
    res = _upload(client, "data.geojson", b'{"type":"FeatureCollection","features":[]}')
    assert res.status_code == 400
    assert ".kml" in res.json()["detail"]


def test_blank_filename_rejected(client):
    # Starlette itself rejects an empty multipart filename with 422
    # before the endpoint runs; either way it is a 4xx, never a 500.
    res = client.post("/api/files/", files={"file": ("", b"data")})
    assert res.status_code in (400, 422)


def test_path_separator_filename_stays_in_uuid_dir(client):
    res = _upload(client, "../../evil.kml", SAMPLE_KML)
    assert res.status_code == 200, res.text
    file_id = res.json()["id"]
    assert (Path("uploads") / file_id / "evil.kml").exists()
    assert not Path("evil.kml").exists()


def test_misleading_suffix_validated_by_content(client):
    res = _upload(client, "data.kml.zip", b"plain text, not a zip")
    assert res.status_code == 400


def test_duplicate_archive_entries_rejected(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("layer.txt", "first")
        zf.writestr("layer.txt", "second")
    res = _upload(client, "dup.zip", buf.getvalue())
    assert res.status_code == 400
    assert "Duplicate" in res.json()["detail"]


def test_suspicious_compression_ratio_rejected(client):
    payload = _zip_bytes({"big.bin": b"\x00" * (5 * 1024 * 1024), "note.txt": b"hi"})
    res = _upload(client, "bomb.zip", payload)
    assert res.status_code == 413


def test_upload_size_limit_returns_413(client, monkeypatch):
    monkeypatch.setattr(fh_service, "MAX_UPLOAD_BYTES", 10)
    res = _upload(client, "sample.kml", SAMPLE_KML)
    assert res.status_code == 413
    assert "limit" in res.json()["detail"].lower()


def test_macos_metadata_and_hidden_files_ignored(client, tmp_path):
    work = tmp_path / "meta"
    _write_shp(_poly_gdf(), work)
    entries = {f"layer/{k}": v for k, v in _shp_entries(work).items()}
    entries["__MACOSX/._layer.shp"] = b"meta"
    entries["__MACOSX/layer.shp"] = b"meta"
    entries["layer/.DS_Store"] = b"meta"
    entries["layer/notes.txt"] = b"unrelated"
    entries["layer/._layer.shx"] = b"meta"
    res = _upload(client, "meta.zip", _zip_bytes(entries))
    assert res.status_code == 200, res.text
    assert res.json()["feature_count"] == 1


def test_mismatched_companion_basenames_rejected(client, tmp_path):
    work = tmp_path / "mismatch"
    _write_shp(_poly_gdf(), work)
    entries = {}
    for name, data in _shp_entries(work).items():
        entries[f"layer/{name}"] = data
    # Move the .dbf under a foreign basename.
    dbf = entries.pop("layer/layer.dbf")
    entries["layer/foreign.dbf"] = dbf
    res = _upload(client, "mismatch.zip", _zip_bytes(entries))
    assert res.status_code == 400
    assert ".dbf" in res.json()["detail"]


def test_missing_shx_rejected(client, tmp_path):
    work = tmp_path / "noshx"
    _write_shp(_poly_gdf(), work)
    entries = {k: v for k, v in _shp_entries(work).items() if not k.endswith(".shx")}
    res = _upload(client, "noshx.zip", _zip_bytes(entries))
    assert res.status_code == 400
    assert ".shx" in res.json()["detail"]


def test_components_across_directories_rejected(client, tmp_path):
    work = tmp_path / "split"
    _write_shp(_poly_gdf(), work)
    entries = {}
    for name, data in _shp_entries(work).items():
        prefix = "a/" if name == "layer.shp" else "b/"
        entries[prefix + name] = data
    res = _upload(client, "split.zip", _zip_bytes(entries))
    assert res.status_code == 400


def test_duplicate_entries_case_insensitive(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("LAYER.TXT", "first")
        zf.writestr("layer.txt", "second")
    res = _upload(client, "dup.zip", buf.getvalue())
    assert res.status_code == 400
    assert "Duplicate" in res.json()["detail"]


# ---------- Geospatial validation ----------

def test_empty_shapefile_rejected(client, tmp_path):
    work = tmp_path / "emptyrows"
    empty = gpd.GeoDataFrame({"name": []}, geometry=[], crs="EPSG:4326")
    _write_shp(empty, work)
    res = _upload(client, "empty.zip", _zip_bytes(_shp_entries(work)))
    assert res.status_code == 400
    assert "No features" in res.json()["detail"]
    assert res.json()["detail"].find("uploads") == -1


def test_garbage_prj_rejected(client, tmp_path):
    work = tmp_path / "badprj"
    _write_shp(_poly_gdf(), work)
    (work / "layer.prj").write_text("THIS IS NOT A CRS {{{ garbage")
    res = _upload(client, "badprj.zip", _zip_bytes(_shp_entries(work)))
    assert res.status_code == 400
    assert "CRS" in res.json()["detail"]


def test_invalid_geometry_stored_without_repair(client, tmp_path):
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
    assert not bowtie.is_valid
    work = tmp_path / "bowtie"
    _write_shp(gpd.GeoDataFrame({"n": ["b"]}, geometry=[bowtie], crs="EPSG:4326"), work)
    res = _upload(client, "bowtie.zip", _zip_bytes(_shp_entries(work)))
    assert res.status_code == 200, res.text
    feat = client.get(f"/api/files/{res.json()['id']}/measurements/").json()["features"][0]
    assert feat["geometry"] is not None  # topology untouched
    assert feat["measurement"] is None or math.isfinite(feat["measurement"]["value"])


def test_z_geometry_accepted(client, tmp_path):
    pz = Polygon(
        [(77.59, 12.97, 5), (77.60, 12.97, 5), (77.60, 12.98, 5), (77.59, 12.97, 5)]
    )
    work = tmp_path / "zgeom"
    _write_shp(gpd.GeoDataFrame({"n": ["z"]}, geometry=[pz], crs="EPSG:4326"), work)
    res = _upload(client, "z.zip", _zip_bytes(_shp_entries(work)))
    assert res.status_code == 200, res.text
    feat = client.get(f"/api/files/{res.json()['id']}/measurements/").json()["features"][0]
    assert feat["measurement"]["type"] == "area"
    assert feat["measurement"]["value"] > 0
    assert len(feat["geometry"]["coordinates"][0][0]) == 3  # Z preserved


def test_nan_coordinates_rejected_unit():
    bad = Polygon([(77.59, 12.97), (float("nan"), 12.98), (77.60, 12.97)])
    gdf = gpd.GeoDataFrame({"n": ["x"]}, geometry=[bad], crs="EPSG:4326")
    try:
        validate_service.validate_dataset(gdf)
    except ValueError as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("NaN coordinates must be rejected")


def test_nan_kml_rejected_without_500(client):
    res = _upload(client, "nan.kml", NAN_KML)
    assert res.status_code == 400
    assert "Traceback" not in res.json()["detail"]


def test_geometrycollection_stored_with_null_measurement(client):
    res = _upload(client, "multi.kml", MULTI_KML)
    assert res.status_code == 200, res.text
    feat = client.get(f"/api/files/{res.json()['id']}/measurements/").json()["features"][0]
    assert feat["geometry_type"] == "GeometryCollection"
    assert feat["measurement"] is None


def test_null_geometry_only_dataset_rejected(client):
    # A dataset with no usable geometry at all is rejected as a whole.
    res = _upload(client, "nogeom.kml", NOGEOM_KML)
    assert res.status_code == 400
    assert "usable geometry" in res.json()["detail"]


def test_single_null_geometry_tolerated(client):
    # ...while one null feature among usable ones is stored with nulls.
    res = _upload(client, "mixednull.kml", MIXED_NULL_KML)
    assert res.status_code == 200, res.text
    feats = client.get(f"/api/files/{res.json()['id']}/measurements/").json()["features"]
    assert len(feats) == 2
    nulls = [f for f in feats if f["geometry"] is None]
    assert len(nulls) == 1 and nulls[0]["measurement"] is None


def test_all_null_geometries_rejected_unit():
    gdf = gpd.GeoDataFrame({"n": ["x", "y"]}, geometry=[None, None], crs="EPSG:4326")
    try:
        validate_service.validate_dataset(gdf)
    except ValueError as exc:
        assert "no usable geometry" in str(exc).lower()
    else:
        raise AssertionError("all-null geometries must be rejected")


def test_empty_kml_rejected_safely(client):
    res = _upload(client, "empty.kml", EMPTY_DOC_KML)
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "Traceback" not in detail
    assert "uploads" not in detail


def test_polar_geometry_rejected_as_400(client, tmp_path):
    polar = Polygon([(0, 85), (1, 85), (1, 86), (0, 86)])
    work = tmp_path / "polar"
    _write_shp(gpd.GeoDataFrame({"n": ["p"]}, geometry=[polar], crs="EPSG:4326"), work)
    res = _upload(client, "polar.zip", _zip_bytes(_shp_entries(work)))
    assert res.status_code == 400
    assert "UTM" in res.json()["detail"]


def test_custom_lcc_crs_end_to_end(client, tmp_path):
    from pyproj import CRS

    lcc = CRS(
        "+proj=lcc +lat_1=12.4729444 +lat_2=35.1728055 +lat_0=24 "
        "+lon_0=80 +x_0=4000000 +y_0=4000000 +datum=WGS84 +units=m +no_defs"
    )
    gdf = _poly_gdf("EPSG:4326").to_crs(lcc)
    work = tmp_path / "lcc"
    _write_shp(gdf, work)
    res = _upload(client, "lcc.zip", _zip_bytes(_shp_entries(work)))
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["crs"]) > 32  # full custom CRS preserved, not truncated
    feat = client.get(f"/api/files/{body['id']}/measurements/").json()["features"][0]
    assert feat["measurement"]["type"] == "area"
    assert math.isfinite(feat["measurement"]["value"])
    assert feat["measurement"]["value"] > 0
    lon, lat = feat["display_geometry"]["coordinates"][0][0][:2]
    assert 77.0 < lon < 78.5 and 12.0 < lat < 14.0


def test_feature_count_limit_returns_413(client, monkeypatch):
    monkeypatch.setattr(validate_service, "MAX_FEATURES", 2)
    res = _upload(client, "mixed.kml", Path("sample_data/mixed.kml").read_bytes())
    assert res.status_code == 413


def test_inf_attributes_become_null():
    assert to_json_safe(float("inf")) is None
    assert to_json_safe(float("-inf")) is None
    assert to_json_safe(float("nan")) is None
    import numpy as np

    assert to_json_safe(np.inf) is None


# ---------- Persistence and API errors ----------

def test_save_failure_marks_failed_without_partials(client, db_session, monkeypatch):
    before = {
        r.id for r in db_session.query(FileRecord).filter(FileRecord.filename == "sample.kml").all()
    }
    real_add_all = Session.add_all

    def boom(self, records):
        if any(isinstance(r, FeatureRecord) for r in records):
            raise RuntimeError("disk on fire")
        return real_add_all(self, records)

    monkeypatch.setattr(Session, "add_all", boom)
    res = _upload(client, "sample.kml", SAMPLE_KML)
    assert res.status_code == 500
    assert res.json()["detail"] == "Could not process the uploaded file."
    after = db_session.query(FileRecord).filter(FileRecord.filename == "sample.kml").all()
    new_rows = [r for r in after if r.id not in before]
    assert len(new_rows) == 1 and new_rows[0].status == "FAILED"
    assert (
        db_session.query(FeatureRecord)
        .filter(FeatureRecord.file_id == new_rows[0].id)
        .count()
        == 0
    )


def test_commit_failure_is_atomic(client, db_session, monkeypatch):
    real_commit = Session.commit
    calls = {"n": 0}

    def flaky(self):
        calls["n"] += 1
        if calls["n"] == 2:
            raise Exception("db down")
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", flaky)
    res = _upload(client, "atomic.kml", SAMPLE_KML)
    assert res.status_code == 500
    rows = db_session.query(FileRecord).filter(FileRecord.filename == "atomic.kml").all()
    assert len(rows) == 1 and rows[0].status == "FAILED"
    assert (
        db_session.query(FeatureRecord).filter(FeatureRecord.file_id == rows[0].id).count() == 0
    )


def test_failed_upload_then_valid_upload(client, db_session):
    bad = _upload(client, "bad.zip", b"not a zip at all")
    assert bad.status_code == 400
    good = _upload(client, "sample.kml", SAMPLE_KML)
    assert good.status_code == 200
    assert good.json()["status"] == "COMPLETED"


def test_error_bodies_hide_internals(client):
    res = _upload(client, "broken.kml", b"<kml>not really kml {{{")
    assert res.status_code in (400, 500)
    body = res.text
    assert "Traceback" not in body
    assert "uploads" not in body
    assert "DATABASE_URL" not in body
    nf = client.get("/api/files/does-not-exist/")
    assert nf.status_code == 404
    assert "Traceback" not in nf.text
