import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Show our INFO logs in the server output so the upload -> parse ->
# extract -> measure -> store pipeline is visible without reading code.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.api.files import router as files_router
from app.db import Base, engine
from app.models import FileRecord  # noqa: F401 - registers the files table


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables once the application starts, not at import time.

    Importing app.main must never open a network connection: on serverless
    platforms an import-time connect failure (or hang) takes down every
    route, including static pages. A startup failure here still propagates
    loudly instead of being skipped.
    """
    # Skipped during tests, which use their own throwaway database
    # instead of PostgreSQL.
    if os.getenv("TESTING") != "1":
        logger.info("Ensuring database tables exist")
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Geospatial File Measurement API",
    description="API for uploading geospatial files and retrieving measurements.",
    version="0.1.0",
    lifespan=lifespan,
)


app.include_router(files_router)

# Resolved from this file's location so templates/static work no matter
# which directory the server is started from (including serverless).
APP_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Serve the Iteration 3.5 test/visualization page."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
def health_check():
    return {"status": "healthy"}
