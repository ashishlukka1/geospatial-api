"""Post-read dataset validation, before measurement and persistence.

Policy (whole file is rejected with HTTP 400/413 on violation):
- Empty datasets and datasets with no usable (non-null, non-empty)
  geometry are rejected; a single null/empty feature is NOT fatal.
- CRS must be present and parseable; it is never guessed or defaulted
  here (KML defaults to EPSG:4326 at parse time per the KML spec,
  Shapefiles must carry their own CRS).
- Non-finite coordinates (NaN, infinity) are rejected: they cannot be
  measured, serialized to JSON, or displayed.
- Feature-count limit guards against pathological collections.

Per-feature policy (documented, unchanged behavior):
- Null or empty geometry is stored with null geometry/measurement.
- Unsupported geometry types (e.g. GeometryCollection) are stored
  with a null measurement; points likewise per the API contract.
- Invalid (self-intersecting) geometries are NOT repaired; their
  measurements are best-effort Shapely results.
- Z coordinates are preserved in storage; measurements use 2D.
"""

import logging
import math
import os

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from app.services.file_handler import PayloadTooLargeError

logger = logging.getLogger(__name__)

MAX_FEATURES = int(os.getenv("MAX_FEATURES", "20000"))


def _iter_coords(geometry: BaseGeometry):
    """Yield every coordinate tuple of a geometry, any dimension."""
    if geometry is None or geometry.is_empty:
        return
    geom_type = geometry.geom_type
    if geom_type == "Point":
        yield geometry.coords[0]
    elif geom_type in ("LineString", "LinearRing"):
        yield from geometry.coords
    elif geom_type in ("Polygon",):
        yield from geometry.exterior.coords
        for ring in geometry.interiors:
            yield from ring.coords
    elif geom_type.startswith("Multi") or geom_type == "GeometryCollection":
        for part in geometry.geoms:
            yield from _iter_coords(part)
    else:
        try:
            yield from geometry.coords  # type: ignore[union-attr]
        except Exception:
            return


def has_finite_coords(geometry: BaseGeometry | None) -> bool:
    """Return False if any coordinate is NaN or infinite (or geometry is None)."""
    if geometry is None or geometry.is_empty:
        return True
    try:
        for coord in _iter_coords(geometry):
            for value in coord:
                if not math.isfinite(value):
                    return False
    except Exception:
        return False
    return True


def validate_dataset(gdf: gpd.GeoDataFrame) -> None:
    """Reject unusable datasets with a clear ValueError/PayloadTooLargeError."""
    if gdf is None or not hasattr(gdf, "geometry"):
        raise ValueError("No geospatial data found in the uploaded file.")
    if len(gdf) == 0:
        raise ValueError("No features found in the uploaded file.")
    if len(gdf) > MAX_FEATURES:
        raise PayloadTooLargeError(
            f"File contains {len(gdf)} features, exceeding the {MAX_FEATURES}-feature limit."
        )
    if gdf.crs is None:
        raise ValueError("Dataset CRS is missing or unknown.")
    try:
        _ = str(gdf.crs)
        gpd.GeoSeries([], crs=gdf.crs)
    except Exception as exc:
        raise ValueError(f"Dataset CRS is invalid: {exc}") from exc
    geometries = list(gdf.geometry)
    usable = [
        g for g in geometries if g is not None and not getattr(g, "is_empty", False)
    ]
    if not usable:
        raise ValueError("Dataset contains no usable geometry.")
    for index, geometry in enumerate(geometries):
        if geometry is not None and not has_finite_coords(geometry):
            raise ValueError(
                f"Feature {index} has non-finite coordinates (NaN or infinity)."
            )
