"""Upload validation, file storage, and file-record helpers."""

from pathlib import Path

from sqlalchemy.orm import Session

from app.models import FileRecord, FileStatus

UPLOAD_DIR = Path("uploads")
ALLOWED_EXTENSIONS = {".kml"}


def validate_upload(filename: str, content: bytes) -> None:
    """Reject non-KML filenames and empty files with a clear message."""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only .kml files are accepted.")
    if len(content) == 0:
        raise ValueError("Uploaded file is empty.")


def save_upload_file(file_id: str, filename: str, content: bytes) -> str:
    """Save uploaded bytes under uploads/<file_id>/ and return the path.

    The directory comes from our own UUID, never from the user's
    filename, so a malicious filename cannot escape the folder.
    """
    folder = UPLOAD_DIR / file_id
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "upload.kml"
    saved_path = folder / safe_name
    saved_path.write_bytes(content)
    return str(saved_path)


def create_processing_record(db: Session, file_id: str, filename: str) -> FileRecord:
    """Insert a new files row with status PROCESSING."""
    record = FileRecord(id=file_id, filename=filename, status=FileStatus.PROCESSING)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def mark_completed(db: Session, record: FileRecord, feature_count: int, crs: str) -> None:
    """Move a record from PROCESSING to COMPLETED with its results."""
    record.status = FileStatus.COMPLETED
    record.feature_count = feature_count
    record.crs = crs
    db.commit()


def mark_failed(db: Session, record: FileRecord, error_message: str) -> None:
    """Move a record from PROCESSING to FAILED with a short message."""
    record.status = FileStatus.FAILED
    record.error_message = error_message
    db.commit()
