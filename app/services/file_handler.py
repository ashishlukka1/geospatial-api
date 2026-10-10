"""Upload validation, file storage, and file-record helpers."""

import logging
import os
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models import FeatureRecord, FileRecord, FileStatus

logger = logging.getLogger(__name__)

# Uploaded bytes are kept only for parsing (features live in the DB).
# Resolved from this file's location; override with UPLOAD_DIR, e.g.
# UPLOAD_DIR=/tmp/uploads on read-only serverless filesystems.
UPLOAD_DIR = Path(
    os.getenv(
        "UPLOAD_DIR",
        str(Path(__file__).resolve().parents[2] / "uploads"),
    )
)
ALLOWED_EXTENSIONS = {".kml", ".zip"}

# Hard cap on the raw request body we will buffer. Larger uploads are
# rejected with HTTP 413 without being fully loaded into memory.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
_READ_CHUNK = 64 * 1024


class PayloadTooLargeError(ValueError):
    """Raised when an upload exceeds a configured size limit (HTTP 413)."""


def validate_upload(filename: str, content: bytes) -> None:
    """Reject missing filenames, unsupported extensions, and empty files."""
    if not filename or not filename.strip():
        raise ValueError("Filename is missing.")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only .kml and .zip files are accepted.")
    if len(content) == 0:
        raise ValueError("Uploaded file is empty.")


async def read_upload_bytes(upload: UploadFile) -> bytes:
    """Read an upload in chunks, enforcing MAX_UPLOAD_BYTES.

    Stops reading as soon as the limit is exceeded so a huge body is
    never fully buffered. Raises PayloadTooLargeError (HTTP 413).
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise PayloadTooLargeError(
                f"Upload exceeds the {MAX_UPLOAD_BYTES}-byte size limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def save_upload_file(file_id: str, filename: str, content: bytes) -> str:
    """Save uploaded bytes under uploads/<file_id>/ and return the path.

    The directory comes from our own UUID, never from the user's
    filename, so a malicious filename cannot escape the folder.
    Only the basename of the user filename is used.
    """
    folder = UPLOAD_DIR / file_id
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "upload"
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


def complete_with_features(
    db: Session,
    record: FileRecord,
    records: list[FeatureRecord],
    crs: str,
) -> None:
    """Persist features and mark the file COMPLETED in a single commit.

    All-or-nothing: if the commit fails, the session is rolled back so
    no partially persisted features remain, and the error propagates
    for the caller to record a FAILED status on a fresh transaction.
    """
    try:
        db.add_all(records)
        record.status = FileStatus.COMPLETED
        record.feature_count = len(records)
        record.crs = crs
        db.commit()
    except Exception:
        db.rollback()
        raise


def mark_completed(db: Session, record: FileRecord, feature_count: int, crs: str) -> None:
    """Move a record from PROCESSING to COMPLETED with its results."""
    record.status = FileStatus.COMPLETED
    record.feature_count = feature_count
    record.crs = crs
    db.commit()


def mark_failed(db: Session, record: FileRecord, error_message: str) -> None:
    """Move a record from PROCESSING to FAILED with a short message.

    Rolls back first so it works on a session left broken by a failed
    commit. Never raises: a status-update failure is logged but must
    not mask the original processing error.
    """
    try:
        db.rollback()
        db.add(record)
        record.status = FileStatus.FAILED
        record.error_message = error_message
        db.commit()
    except Exception:
        logger.warning("Could not mark file %s as FAILED", record.id, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
