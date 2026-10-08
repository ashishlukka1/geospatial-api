"""File upload and file information endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FeatureRecord, FileRecord
from app.schemas import FileResponse, MeasurementsResponse
from app.services import features, file_handler
from app.services.parser import parse_kml_file

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/", response_model=FileResponse)
async def upload_file(file: UploadFile, db: Session = Depends(get_db)):
    """Accept a KML file, store it, parse it, and return its record."""
    content = await file.read()
    filename = file.filename or "upload.kml"
    try:
        file_handler.validate_upload(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    file_id = str(uuid.uuid4())
    saved_path = file_handler.save_upload_file(file_id, filename, content)
    record = file_handler.create_processing_record(db, file_id, filename)

    try:
        gdf = parse_kml_file(saved_path)
        crs_name = str(gdf.crs) if gdf.crs is not None else "EPSG:4326"
        extracted = features.extract_features(file_id, gdf, crs_name)
        features.save_features(db, file_id, extracted)
    except ValueError as exc:
        file_handler.mark_failed(db, record, str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        file_handler.mark_failed(db, record, "Could not process the uploaded file.")
        raise HTTPException(status_code=500, detail="Could not process the uploaded file.")

    file_handler.mark_completed(db, record, len(gdf), crs_name)
    return record


@router.get("/{file_id}/", response_model=FileResponse)
def get_file_info(file_id: str, db: Session = Depends(get_db)):
    """Return the stored information for one uploaded file."""
    record = db.get(FileRecord, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return record


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def get_measurements(file_id: str, db: Session = Depends(get_db)):
    """Return the stored features of one uploaded file.

    Reads from the features table; the KML is never reparsed here.
    Measurements stay null until Iteration 3.
    """
    record = db.get(FileRecord, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    rows = (
        db.query(FeatureRecord)
        .filter(FeatureRecord.file_id == file_id)
        .order_by(FeatureRecord.feature_index)
        .all()
    )
    return {"file_id": file_id, "features": rows}
