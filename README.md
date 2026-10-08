# Geospatial File Measurement API

API for uploading geospatial files (KML and zipped Shapefiles) and retrieving measurements such as polygon area and line length.

## Technology Stack

- Python 3.11+
- FastAPI
- Uvicorn
- SQLAlchemy
- SQLite
- GeoPandas
- Shapely
- pyproj
- python-multipart
- pytest

## Local Setup

1. Create a virtual environment:

```bash
python -m venv venv
```

2. Activate the virtual environment:

```bash
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the FastAPI server (from the project root folder `aereo-2`):

```bash
uvicorn app.main:app --reload
```

5. Open in your browser:

- API root: http://127.0.0.1:8000/
- Interactive docs: http://127.0.0.1:8000/docs
