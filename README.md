# Geospatial File Measurement API

API for uploading geospatial files (KML and zipped Shapefiles) and retrieving measurements such as polygon area and line length.

## Technology Stack

- Python 3.11+
- FastAPI
- Uvicorn
- SQLAlchemy
- Supabase PostgreSQL (production) / SQLite (tests)
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

4. Add a `.env` file with your Supabase connection string:

```bash
DATABASE_URL=postgresql://...
```

Optional limits (defaults shown):

```bash
MAX_UPLOAD_BYTES=26214400
SHAPEFILE_MAX_UNCOMPRESSED_BYTES=104857600
SHAPEFILE_MAX_COMPRESSION_RATIO=200
MAX_FEATURES=20000
```

5. Run the FastAPI server (from the project root folder `aereo-2`):

```bash
uvicorn app.main:app --reload
```

6. Open in your browser:

- Viewer: http://127.0.0.1:8000/
- Interactive docs: http://127.0.0.1:8000/docs

## Supported formats

- `.kml` — coordinates are WGS84 per the KML spec (stored as EPSG:4326).
- `.zip` containing exactly one Shapefile layer: one `.shp` with matching
  `.shx` and `.dbf` in the same directory (same basename, case-insensitive).
  The layer may sit at the ZIP root or in a nested directory. Only the
  layer's own sidecars (`.shp/.shx/.dbf/.prj/.cpg/.qix/.sbn/.sbx`) are
  extracted; `__MACOSX/`, `._*`, hidden, and unrelated files are ignored.
  Multiple `.shp` files are rejected with a clear error — the API never
  silently picks the first layer.

## Size and resource limits

- Raw upload body: `MAX_UPLOAD_BYTES` (default 25 MB) → HTTP 413. Uploads are
  read in chunks so an oversized body is never fully buffered.
- Total uncompressed ZIP size: `SHAPEFILE_MAX_UNCOMPRESSED_BYTES`
  (default 100 MB, checked before and during extraction) → HTTP 413.
- Suspicious compression ratio (>200x on entries larger than 1 MB) → HTTP 413.
- Feature count: `MAX_FEATURES` (default 20000) → HTTP 413.

These are application-level guards, not complete DoS protection. For
production, also enforce request-size limits at the reverse proxy
(nginx `client_max_body_size`, or equivalent) since the app reads the
body before the framework applies any limit.

## CRS and measurement strategy

- The original source CRS is preserved verbatim (PostgreSQL `TEXT` columns,
  including long custom WKT such as Lambert Conformal Conic). It is never
  truncated, guessed, or silently replaced with EPSG:4326.
- Shapefiles without a readable CRS are rejected (HTTP 400).
- Area (Polygon/MultiPolygon, m²) and length (LineString/MultiLineString, m)
  are always computed on a UTM reprojection in meters, never in degrees.
  The UTM zone is selected from a WGS84 copy of each geometry.
- Points (and MultiPoints) carry a null measurement per the API contract —
  no zero values are fabricated.
- Unsupported geometry types (e.g. GeometryCollection) are stored with a
  null measurement; invalid (self-intersecting) geometries are stored
  unrepaired with best-effort measurements. Null/empty geometries are
  stored with nulls; a dataset with no usable geometry at all is rejected.
- Non-finite coordinates (NaN/infinity) and non-finite results are rejected
  or nulled rather than persisted.
- Each feature also exposes `display_geometry`: a copy reprojected to
  EPSG:4326 for the Leaflet map. Source geometry and measurements are
  never modified for display; if display reprojection fails, the source
  geometry is returned with a server-side warning.

## Errors

- `400` malformed/unsupported content (bad KML/ZIP, missing components,
  bad geometry/CRS, unknown file has its own `404`).
- `413` exceeding a configured size limit.
- `404` unknown file ID.
- `500` unexpected processing/persistence failure (generic message only).

Error bodies never include tracebacks, SQL, filesystem paths, or secrets.
Failed uploads are recorded as `FAILED`; features and the `COMPLETED`
status are persisted in a single transaction, so failures leave no
partial feature rows.

## Running tests

```bash
.\venv\Scripts\python.exe -m pytest -q
```

Tests use an in-memory SQLite database and synthetic fixtures only — no
live Supabase connection or network access required.

## Known limitations / future work

- No authentication, pagination, or async/background processing.
- Request-size enforcement inside the app happens after the ASGI server
  buffers headers; pair with proxy-level limits (see above).
- ZIP-bomb defense is heuristic (size + ratio caps), not a guarantee.
- Extremely large (but under-limit) files are processed synchronously and
  can tie up a worker; a job queue would be the next step if needed.
