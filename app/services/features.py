"""Per-feature extraction from a parsed GeoDataFrame.

Turns each GeoPandas row into a plain dict (index, geometry type,
GeoJSON geometry, CRS, JSON-safe properties) and persists those
dicts as FeatureRecord rows linked to the uploaded file.
"""

import logging
import math
import uuid
from datetime import date, datetime
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import mapping
from sqlalchemy.orm import Session

from app.models import FeatureRecord
from app.services.measure import measure_feature

logger = logging.getLogger(__name__)


def to_json_safe(value: Any) -> Any:
    """Convert one value so it can be stored as JSON and returned by FastAPI."""
    if value is None:
        return None
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, str):
        return value
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return [to_json_safe(item) for item in value.tolist()]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_safe(item) for item in value]
    return str(value)


def extract_features(file_id: str, gdf: gpd.GeoDataFrame, crs_name: str) -> list[dict]:
    """Build one plain dict per GeoDataFrame row for the given file.

    Each dict also carries the UTM measurement result (or null fields
    for points and unsupported types). The source geometry is kept
    unchanged; only measurement metadata is added.
    """
    logger.info("Extracting features for file %s", file_id)
    geometry_column = gdf.geometry.name
    extracted: list[dict] = []
    for feature_index, (_, row) in enumerate(gdf.iterrows()):
        geometry = row.geometry
        properties = {
            column: to_json_safe(row[column])
            for column in gdf.columns
            if column != geometry_column
        }
        measurement = measure_feature(file_id, feature_index, geometry)
        extracted.append(
            {
                "feature_index": feature_index,
                "geometry_type": geometry.geom_type if geometry is not None else None,
                "geometry": mapping(geometry) if geometry is not None else None,
                "crs": crs_name,
                "properties": properties,
                "projected_crs": measurement["projected_crs"] if measurement else None,
                "measurement_type": measurement["type"] if measurement else None,
                "measurement_value": measurement["value"] if measurement else None,
                "measurement_unit": measurement["unit"] if measurement else None,
            }
        )
    logger.info("Extracted %d features for file %s", len(extracted), file_id)
    return extracted


def save_features(db: Session, file_id: str, extracted: list[dict]) -> int:
    """Persist extracted feature dicts as FeatureRecord rows for the file."""
    records = [
        FeatureRecord(
            id=str(uuid.uuid4()),
            file_id=file_id,
            feature_index=item["feature_index"],
            geometry_type=item["geometry_type"],
            geometry=item["geometry"],
            crs=item["crs"],
            properties=item["properties"],
            projected_crs=item["projected_crs"],
            measurement_type=item["measurement_type"],
            measurement_value=item["measurement_value"],
            measurement_unit=item["measurement_unit"],
        )
        for item in extracted
    ]
    db.add_all(records)
    db.commit()
    logger.info("Stored %d features for file %s", len(records), file_id)
    return len(records)


def build_measurements_response(file_id: str, rows: list[FeatureRecord]) -> dict:
    """Shape stored rows into the measurements response with nested measurement."""
    features = []
    for row in rows:
        if row.measurement_type is None:
            measurement = None
        else:
            measurement = {
                "type": row.measurement_type,
                "value": row.measurement_value,
                "unit": row.measurement_unit,
            }
        features.append(
            {
                "feature_index": row.feature_index,
                "geometry_type": row.geometry_type,
                "geometry": row.geometry,
                "crs": row.crs,
                "properties": row.properties,
                "projected_crs": row.projected_crs,
                "measurement": measurement,
            }
        )
    return {"file_id": file_id, "features": features}
