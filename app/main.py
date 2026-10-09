import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Serve the Iteration 3.5 test/visualization page."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
def health_check():
    return {"status": "healthy"}
