"""Area/length measurement in meters via UTM reprojection.

Flow per feature: WGS84 geometry -> choose UTM CRS -> reproject with
GeoPandas (CRS-aware, no manual coordinate math) -> Shapely area/length
on the projected meters grid. Points and unknown types return None.
"""

import logging

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from app.services.crs import choose_utm_crs

logger = logging.getLogger(__name__)

SOURCE_CRS = "EPSG:4326"
AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}


def measure_feature(file_id: str, feature_index: int, geometry: BaseGeometry | None) -> dict | None:
    """Measure one geometry, returning UTM + measurement info or None."""
    geometry_type = geometry.geom_type if geometry is not None else None
    logger.info("Processing feature %d for file %s", feature_index, file_id)
    logger.info("Feature %d geometry type: %s", feature_index, geometry_type)
    logger.info("Feature %d CRS: %s", feature_index, SOURCE_CRS)
    if geometry is None or geometry_type in POINT_TYPES:
        logger.info("Feature %d measurement not applicable", feature_index)
        return None
    if geometry_type not in AREA_TYPES and geometry_type not in LENGTH_TYPES:
        logger.info("Feature %d has unsupported type %s; skipping measurement", feature_index, geometry_type)
        return None
    projected_crs = choose_utm_crs(geometry)
    logger.info("Feature %d projected CRS: %s", feature_index, projected_crs)
    projected = gpd.GeoSeries([geometry], crs=SOURCE_CRS).to_crs(projected_crs).iloc[0]
    if geometry_type in AREA_TYPES:
        value = float(projected.area)
        logger.info("Feature %d area: %.2f m\u00b2", feature_index, value)
        return {"projected_crs": projected_crs, "type": "area", "value": value, "unit": "m\u00b2"}
    value = float(projected.length)
    logger.info("Feature %d length: %.2f m", feature_index, value)
    return {"projected_crs": projected_crs, "type": "length", "value": value, "unit": "m"}
