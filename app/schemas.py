"""Pydantic models for API requests and responses."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import FileStatus


class FileResponse(BaseModel):
    """What the API returns for one uploaded file."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: int | None = None
    crs: str | None = None
    status: FileStatus


class Measurement(BaseModel):
    """A calculated area or length. Value is rounded for presentation.

    The database keeps full precision; only the API response rounds.
    """

    type: str
    value: float
    unit: str

    @field_validator("value")
    @classmethod
    def round_to_two_places(cls, value: float) -> float:
        """Round the presented value to two decimals, keeping the unit."""
        return round(value, 2)


class FeatureResponse(BaseModel):
    """One stored feature with its measurement (null for points)."""

    model_config = ConfigDict(from_attributes=True)

    feature_index: int
    geometry_type: str | None = None
    geometry: dict | None = None
    crs: str
    properties: dict = {}
    projected_crs: str | None = None
    measurement: Measurement | None = None


class MeasurementsResponse(BaseModel):
    """All stored features of one uploaded file."""

    file_id: str
    features: list[FeatureResponse]
