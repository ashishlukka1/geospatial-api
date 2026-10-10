"""Regression tests for long/custom CRS storage and display reprojection.

SQLite does not enforce VARCHAR lengths, so these tests assert the
model column types directly plus the full-string roundtrip and the
EPSG:4326 display geometry used by Leaflet.
"""

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon
from sqlalchemy import Text

from app.models import FeatureRecord, FileRecord
from app.services.features import to_display_geometry

LONG_CRS = (
    'PROJCS["WGS_1984_Lambert_Conformal_Conic",GEOGCS["WGS 84",'
    'DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Lambert_Conformal_Conic_2SP"],'
    'PARAMETER["latitude_of_origin",24],PARAMETER["central_meridian",80],'
    'UNIT["metre",1]]'
)
assert len(LONG_CRS) > 32

SAMPLE_KML = Path("sample_data/sample.kml").read_bytes()


def _poly_gdf(crs="EPSG:4326"):
    poly = Polygon(
        [(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98)]
    )
    return gpd.GeoDataFrame({"name": ["a"]}, geometry=[poly], crs=crs)


def test_crs_columns_are_text():
    """The 32-char VARCHAR limit caused live StringDataRightTruncation."""
    assert isinstance(FileRecord.__table__.c.crs.type, Text)
    assert isinstance(FeatureRecord.__table__.c.crs.type, Text)


def test_long_crs_roundtrip(client, db_session):
    """A >32-char CRS string persists in full and is returned as-is."""
    from app.services import features

    file_id = "long-crs-file"
    gdf_utm = _poly_gdf("EPSG:4326").to_crs("EPSG:32643")
    long_crs = gdf_utm.crs.to_wkt()
    assert len(long_crs) > 32
    try:
        extracted = features.extract_features(file_id, gdf_utm, long_crs)
        assert extracted[0]["crs"] == long_crs
        rec = FileRecord(id=file_id, filename="long.zip", status="COMPLETED")
        db_session.add(rec)
        db_session.commit()
        features.save_features(db_session, file_id, extracted)
        row = (
            db_session.query(FeatureRecord)
            .filter(FeatureRecord.file_id == file_id)
            .one()
        )
        assert row.crs == long_crs
        body = features.build_measurements_response(file_id, [row])
        assert body["features"][0]["crs"] == long_crs
    finally:
        db_session.query(FeatureRecord).filter(FeatureRecord.file_id == file_id).delete()
        db_session.query(FileRecord).filter(FileRecord.id == file_id).delete()
        db_session.commit()


def test_display_geometry_reprojects_projected_source():
    """Projected source coords become lon/lat for Leaflet display."""
    gdf_utm = _poly_gdf("EPSG:4326").to_crs("EPSG:32643")
    geom = gdf_utm.geometry.iloc[0].__geo_interface__
    assert abs(geom["coordinates"][0][0][0]) > 1000  # easting, not longitude
    disp = to_display_geometry(geom, "EPSG:32643")
    lon, lat = disp["coordinates"][0][0][:2]
    assert -180 <= lon <= 180 and -90 <= lat <= 90
    assert abs(lon - 77.595) < 0.05 and abs(lat - 12.975) < 0.05


def test_display_geometry_passthrough_for_4326():
    geom = _poly_gdf().geometry.iloc[0].__geo_interface__
    assert to_display_geometry(geom, "EPSG:4326") == geom


def test_measurements_include_display_geometry(client, tmp_path):
    """API contract: geometry (source) + display_geometry (4326)."""
    import zipfile

    work = tmp_path / "disp"
    work.mkdir(exist_ok=True)
    _poly_gdf("EPSG:4326").to_crs("EPSG:32643").to_file(work / "layer.shp")
    dest = tmp_path / "disp.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in work.rglob("*"):
            if p.is_file():
                zf.write(p, p.name)
    up = client.post("/api/files/", files={"file": ("disp.zip", dest.read_bytes())})
    assert up.status_code == 200
    feat = client.get(f"/api/files/{up.json()['id']}/measurements/").json()["features"][0]
    assert feat["crs"] == "EPSG:32643"
    assert feat["geometry"] != feat["display_geometry"]
    lon = feat["display_geometry"]["coordinates"][0][0][0]
    assert -180 <= lon <= 180


def test_kml_display_matches_source(client):
    """KML stays EPSG:4326: display geometry equals source geometry."""
    file_id = client.post("/api/files/", files={"file": ("sample.kml", SAMPLE_KML)}).json()["id"]
    for feat in client.get(f"/api/files/{file_id}/measurements/").json()["features"]:
        assert feat["crs"] == "EPSG:4326"
        assert feat["display_geometry"] == feat["geometry"]
