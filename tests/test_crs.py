"""Unit tests for UTM CRS selection."""

from shapely.geometry import Point

from app.services.crs import choose_utm_crs


def test_hyderabad_gives_zone_44_north():
    """Hyderabad (lon ~78.4, lat ~17.3) sits in UTM zone 44N."""
    assert choose_utm_crs(Point(78.471, 17.385)) == "EPSG:32644"


def test_southern_hemisphere_uses_327_base():
    """Sydney (lon ~151.2, lat ~-33.8) sits in UTM zone 56S."""
    assert choose_utm_crs(Point(151.21, -33.87)) == "EPSG:32756"


def test_zone_boundary():
    """Longitude 6.0 starts zone 32, just below it is still zone 31."""
    assert choose_utm_crs(Point(6.0, 48.0)) == "EPSG:32632"
    assert choose_utm_crs(Point(5.999, 48.0)) == "EPSG:32631"
