"""UTM CRS selection for meter-based measurement.

Degrees of longitude shrink toward the poles, so an area or length
computed directly in EPSG:4326 is meaningless. UTM projects a narrow
6-degree slice of the earth onto a flat grid in meters, which makes
plain Shapely area/length correct. This module picks the UTM zone
that contains a feature.
"""

from math import floor

from shapely.geometry.base import BaseGeometry


def choose_utm_crs(geometry: BaseGeometry) -> str:
    """Return the UTM EPSG string (e.g. EPSG:32644) for a WGS84 geometry.

    Uses representative_point() because it is guaranteed to lie inside
    the geometry, while centroid() can fall outside concave shapes and
    would then pick the wrong zone. Raises ValueError near the poles,
    where UTM is undefined (|latitude| > 84).
    """
    if geometry is None or geometry.is_empty:
        raise ValueError("Cannot choose a UTM CRS for an empty geometry.")
    point = geometry.representative_point()
    longitude = point.x
    latitude = point.y
    if abs(latitude) > 84:
        raise ValueError("UTM is not defined near the poles.")
    zone = floor((longitude + 180) / 6) + 1
    if latitude >= 0:
        return f"EPSG:{32600 + zone}"
    return f"EPSG:{32700 + zone}"
