"""File upload and file information endpoints."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FeatureRecord, FileRecord
from app.schemas import FileResponse, MeasurementsResponse
from app.services import features, file_handler
from app.services.file_handler import PayloadTooLargeError
from app.services.parser import parse_kml_file
from app.services.shapefile import read_shapefile_zip
from app.services.validate import validate_dataset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


def _safe_detail(exc: Exception, saved_path: str, file_id: str = "") -> str:
    """Build a client-safe error message without filesystem paths.

    Third-party parser errors may embed the absolute upload path (with
    either separator style); only the file's basename is safe to expose.
    """
    text = str(exc) or "Invalid file content."
    if saved_path:
        text = text.replace(saved_path, Path(saved_path).name)
        text = text.replace(saved_path.replace("\\", "/"), Path(saved_path).name)
        text = text.replace("uploads", "upload")
    if file_id:
        text = text.replace(file_id, "file")
    return text


@router.post("/", response_model=FileResponse)
async def upload_file(file: UploadFile, db: Session = Depends(get_db)):
    """Accept a KML or zipped Shapefile, store it, parse it, return its record."""
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is missing.")
    try:
        content = await file_handler.read_upload_bytes(file)
    except PayloadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    try:
        file_handler.validate_upload(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    file_id = str(uuid.uuid4())
    saved_path = file_handler.save_upload_file(file_id, filename, content)
    record = file_handler.create_processing_record(db, file_id, filename)

    try:
        extension = Path(filename).suffix.lower()
        if extension == ".zip":
            gdf = read_shapefile_zip(saved_path)
        else:
            gdf = parse_kml_file(saved_path)
        validate_dataset(gdf)
        crs_name = str(gdf.crs)
        extracted = features.extract_features(file_id, gdf, crs_name)
        records = features.build_feature_records(file_id, extracted)
        file_handler.complete_with_features(db, record, records, crs_name)
    except PayloadTooLargeError as exc:
        file_handler.mark_failed(db, record, str(exc))
        raise HTTPException(status_code=413, detail=str(exc))
    except ValueError as exc:
        detail = _safe_detail(exc, saved_path, file_id)
        file_handler.mark_failed(db, record, detail)
        raise HTTPException(status_code=400, detail=detail)
    except Exception:
        logger.exception("Failed to process upload %s", file_id)
        file_handler.mark_failed(db, record, "Could not process the uploaded file.")
        raise HTTPException(status_code=500, detail="Could not process the uploaded file.")

    return record


@router.get("/{file_id}/", response_model=FileResponse)
def get_file_info(file_id: str, db: Session = Depends(get_db)):
    """Return the stored information for one uploaded file."""
    try:
        record = db.get(FileRecord, file_id)
    except Exception:
        logger.exception("Database lookup failed for file %s", file_id)
        raise HTTPException(status_code=500, detail="Could not retrieve file information.")
    if record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return record


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def get_measurements(file_id: str, db: Session = Depends(get_db)):
    """Return the stored features of one uploaded file.

    Reads from the features table; the source file is never reparsed.
    """
    try:
        record = db.get(FileRecord, file_id)
        if record is None:
            raise HTTPException(status_code=404, detail="File not found.")
        rows = (
            db.query(FeatureRecord)
            .filter(FeatureRecord.file_id == file_id)
            .order_by(FeatureRecord.feature_index)
            .all()
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Database lookup failed for measurements of %s", file_id)
        raise HTTPException(status_code=500, detail="Could not retrieve measurements.")
    return features.build_measurements_response(file_id, rows)
