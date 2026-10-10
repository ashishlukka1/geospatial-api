"""Area/length measurement in meters via UTM reprojection.

Flow per feature: WGS84 geometry -> choose UTM CRS -> reproject with
GeoPandas (CRS-aware, no manual coordinate math) -> Shapely area/length
on the projected meters grid. Points and unknown types return None.
"""

import logging
import math

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from app.services.crs import choose_utm_crs

logger = logging.getLogger(__name__)

SOURCE_CRS = "EPSG:4326"
AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}


def measure_feature(
    file_id: str, feature_index: int, geometry: BaseGeometry | None, source_crs: str = SOURCE_CRS
) -> dict | None:
    """Measure one geometry, returning UTM + measurement info or None.

    source_crs is the CRS of the incoming geometry (EPSG:4326 for KML,
    actual Shapefile CRS otherwise). The geometry is reprojected from
    source_crs to the selected UTM CRS for measurement; UTM zone
    selection always uses a WGS84 copy.
    """
    geometry_type = geometry.geom_type if geometry is not None else None
    logger.info("Processing feature %d for file %s", feature_index, file_id)
    logger.info("Feature %d geometry type: %s", feature_index, geometry_type)
    logger.info("Feature %d CRS: %s", feature_index, source_crs)
    if geometry is None or getattr(geometry, "is_empty", False) or geometry_type in POINT_TYPES:
        logger.info("Feature %d measurement not applicable", feature_index)
        return None
    if geometry_type not in AREA_TYPES and geometry_type not in LENGTH_TYPES:
        logger.info("Feature %d has unsupported type %s; skipping measurement", feature_index, geometry_type)
        return None
    # UTM zone must be picked from lon/lat, so convert to WGS84 first
    # when the source is a projected Shapefile CRS.
    try:
        wgs84_geom = gpd.GeoSeries([geometry], crs=source_crs).to_crs(SOURCE_CRS).iloc[0]
        projected_crs = choose_utm_crs(wgs84_geom)
        logger.info("Feature %d projected CRS: %s", feature_index, projected_crs)
        projected = gpd.GeoSeries([geometry], crs=source_crs).to_crs(projected_crs).iloc[0]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"Feature {feature_index} could not be transformed for measurement: {exc}"
        ) from exc
    if geometry_type in AREA_TYPES:
        value = float(projected.area)
        if not math.isfinite(value):
            logger.info("Feature %d area is not finite; skipping measurement", feature_index)
            return None
        logger.info("Feature %d area: %.2f m\u00b2", feature_index, value)
        return {"projected_crs": projected_crs, "type": "area", "value": value, "unit": "m\u00b2"}
    value = float(projected.length)
    if not math.isfinite(value):
        logger.info("Feature %d length is not finite; skipping measurement", feature_index)
        return None
    logger.info("Feature %d length: %.2f m", feature_index, value)
    return {"projected_crs": projected_crs, "type": "length", "value": value, "unit": "m"}
