import logging
import os

from fastapi import FastAPI

# Show our INFO logs in the server output so the upload -> parse ->
# extract -> measure -> store pipeline is visible without reading code.
logging.basicConfig(level=logging.INFO)

from app.api.files import router as files_router
from app.db import Base, engine
from app.models import FileRecord  # noqa: F401 - registers the files table

app = FastAPI(
    title="Geospatial File Measurement API",
    description="API for uploading geospatial files and retrieving measurements.",
    version="0.1.0",
)

# Create tables when the application starts. Skipped during tests,
# which use their own throwaway database instead of PostgreSQL.
if os.getenv("TESTING") != "1":
    Base.metadata.create_all(bind=engine)

app.include_router(files_router)


@app.get("/")
def read_root():
    return {"message": "Geospatial File Measurement API is running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
