"""Tests for area/length measurement plus the full upload flow.

The known-answer shapes are built as exact meter sizes in UTM zone 44N
(EPSG:32644) and converted back to EPSG:4326, so the test input looks
like real KML coordinates while the expected answer is known.
"""

from pathlib import Path

import geopandas as gpd
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)

from app.services.measure import measure_feature

MIXED_KML = Path("sample_data/mixed.kml").read_bytes()
HYDERABAD_LON = 78.471
HYDERABAD_LAT = 17.385


def utm_point_1km():
    """Centre of Hyderabad expressed in UTM 44N meters."""
    return (
        gpd.GeoSeries([Point(HYDERABAD_LON, HYDERABAD_LAT)], crs="EPSG:4326")
        .to_crs("EPSG:32644")
        .iloc[0]
    )


def square_1km_wgs84():
    """A 1000 m x 1000 m square near Hyderabad, as EPSG:4326 coordinates."""
    center = utm_point_1km()
    east, north = center.x, center.y
    square = Polygon(
        [
            (east - 500, north - 500),
            (east + 500, north - 500),
            (east + 500, north + 500),
            (east - 500, north + 500),
        ]
    )
    return gpd.GeoSeries([square], crs="EPSG:32644").to_crs("EPSG:4326").iloc[0]


def line_1km_wgs84():
    """A 1000 m line near Hyderabad, as EPSG:4326 coordinates."""
    center = utm_point_1km()
    line = LineString([(center.x - 500, center.y), (center.x + 500, center.y)])
    return gpd.GeoSeries([line], crs="EPSG:32644").to_crs("EPSG:4326").iloc[0]


def test_polygon_area_1km_square():
    """Step 15: a 1 km x 1 km square measures about 1,000,000 m2."""
    result = measure_feature("test-file", 0, square_1km_wgs84())
    assert result["projected_crs"] == "EPSG:32644"
    assert result["type"] == "area"
    assert result["unit"] == "m\u00b2"
    assert 990_000 < result["value"] < 1_010_000


def test_linestring_length_1km():
    """A 1 km line measures about 1000 m."""
    result = measure_feature("test-file", 0, line_1km_wgs84())
    assert result["type"] == "length"
    assert result["unit"] == "m"
    assert 990 < result["value"] < 1010


def test_point_has_no_measurement():
    """Points (and multipoints) return None instead of a measurement."""
    assert measure_feature("test-file", 0, Point(78.471, 17.385)) is None
    assert measure_feature("test-file", 0, MultiPoint([(78.4, 17.3)])) is None


def test_multipolygon_area():
    """A MultiPolygon sums the area of its parts."""
    square = square_1km_wgs84()
    multi = MultiPolygon([square, square])
    result = measure_feature("test-file", 0, multi)
    assert result["type"] == "area"
    assert 1_980_000 < result["value"] < 2_020_000


def test_multilinestring_length():
    """A MultiLineString sums the length of its parts."""
    line = line_1km_wgs84()
    multi = MultiLineString([line, line])
    result = measure_feature("test-file", 0, multi)
    assert result["type"] == "length"
    assert 1980 < result["value"] < 2020


def test_unsupported_geometry_does_not_crash():
    """Unknown geometry types return None instead of raising."""
    mixed = GeometryCollection([Point(78.471, 17.385)])
    assert measure_feature("test-file", 0, mixed) is None


def test_full_upload_measures_all_types(client):
    """Step 16: upload Polygon + LineString + Point, verify measurements."""
    upload = client.post("/api/files/", files={"file": ("mixed.kml", MIXED_KML)})
    assert upload.status_code == 200
    file_id = upload.json()["id"]
    assert upload.json()["status"] == "COMPLETED"
    assert upload.json()["feature_count"] == 3

    body = client.get(f"/api/files/{file_id}/measurements/").json()
    polygon, line, point = body["features"]

    assert polygon["projected_crs"] == "EPSG:32644"
    assert polygon["measurement"]["type"] == "area"
    assert polygon["measurement"]["unit"] == "m\u00b2"
    assert polygon["measurement"]["value"] is not None

    assert line["projected_crs"] == "EPSG:32644"
    assert line["measurement"]["type"] == "length"
    assert line["measurement"]["unit"] == "m"
    assert line["measurement"]["value"] is not None

    assert point["measurement"] is None
