"""Pydantic models for API requests and responses."""

from pydantic import BaseModel, ConfigDict

from app.models import FileStatus


class FileResponse(BaseModel):
    """What the API returns for one uploaded file."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: int | None = None
    crs: str | None = None
    status: FileStatus


class FeatureResponse(BaseModel):
    """One stored feature. Measurement stays None until Iteration 3."""

    model_config = ConfigDict(from_attributes=True)

    feature_index: int
    geometry_type: str | None = None
    geometry: dict | None = None
    crs: str
    properties: dict = {}
    measurement: float | None = None


class MeasurementsResponse(BaseModel):
    """All stored features of one uploaded file."""

    file_id: str
    features: list[FeatureResponse]
