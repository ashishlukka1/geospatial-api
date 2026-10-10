# Geospatial File Measurement API

Upload KML files and ZIP-wrapped Shapefiles, persist their features in
PostgreSQL, and retrieve per-feature area/length measurements with full
CRS provenance. A minimal Leaflet page at `/` exercises the real API:
upload a file, inspect its metadata and feature table, and view the
geometries on a map.

## 1. Features

- `POST /api/files/` accepts `.kml` and `.zip` (one Shapefile layer per archive).
- `GET /api/files/{id}/` returns stored file metadata and processing status
  (`PROCESSING` / `COMPLETED` / `FAILED`).
- `GET /api/files/{id}/measurements/` returns every stored feature: GeoJSON
  source geometry, an EPSG:4326 `display_geometry` for the map, source and
  projected CRS, properties, and a nested area/length measurement
  (null for points and unsupported types).
- UTM-based area (m²) and length (m) via CRS-aware reprojection; custom and
  long-WKT CRS definitions are preserved verbatim, never guessed or truncated.
- Hardened uploads: size caps (HTTP 413), path-traversal and duplicate-entry
  rejection, single-layer enforcement, companion-file checks, temp-dir
  extraction with cleanup, atomic persistence, and leak-free error messages.
- Vanilla-JS Leaflet viewer (no frontend framework or build step).

## 2. Technology stack

| Layer | Choice |
|---|---|
| API | FastAPI 0.143, Uvicorn 0.54 |
| Geospatial | GeoPandas, Shapely, pyproj |
| ORM / DB | SQLAlchemy; Supabase PostgreSQL (production), in-memory SQLite (tests) |
| Frontend | Jinja2 template, plain CSS, vanilla JS `fetch()`, Leaflet 1.9.4 via CDN |
| Tests | pytest, httpx `TestClient` |
| Runtime | Python 3.10 (project venv runs 3.10.11) |

Dependencies are listed in `requirements.txt` (unpinned, plus `pytest` and
`httpx` for the suite).

## 3. Architecture and folder structure

```text
aereo-2/
├── app/
│   ├── main.py            # FastAPI app, GET /, GET /health, /static mount
│   ├── db.py              # Engine + session factory, get_db dependency
│   ├── models.py          # files / features tables, FileStatus enum
│   ├── schemas.py         # FileResponse, Measurement, FeatureResponse, MeasurementsResponse
│   ├── api/files.py       # POST /api/files/, GET file info, GET measurements
│   ├── services/
│   │   ├── file_handler.py# upload limits, storage, record + transaction helpers
│   │   ├── parser.py      # KML reading (GeoPandas, KML driver)
│   │   ├── shapefile.py   # ZIP validation, safe selective extraction, .shp reading
│   │   ├── validate.py    # post-read dataset validation
│   │   ├── features.py    # extraction, persistence objects, response shaping, display reprojection
│   │   ├── crs.py         # UTM-zone selection from a WGS84 point
│   │   └── measure.py     # area/length via UTM reprojection
│   ├── templates/index.html
│   └── static/{app.js,style.css}
├── tests/                 # pytest suite (SQLite, synthetic fixtures; see §13)
├── sample_data/           # sample.kml, mixed.kml, polygons.zip
├── requirements.txt
└── .env                   # NOT committed; holds DATABASE_URL (see §5)
```

Request flow: route (thin) → service modules (validation, parsing,
measurement) → single-commit persistence → Pydantic response models.
GET endpoints read persisted rows; source files are never reparsed.

### Architecture diagram

The diagram below illustrates the upload and retrieval flows, including format-specific parsing, dataset validation, CRS-aware measurements, database persistence, and map visualization.

```mermaid
flowchart TD
    U["User / Browser"] --> UI["Leaflet UI<br/>HTML, CSS, JavaScript"]
    UI --> API["FastAPI Application"]

    API --> UP["POST /api/files/"]
    API --> GET["GET file metadata"]
    API --> MEAS["GET measurements"]

    UP --> FH["Upload & Archive Validation"]
    FH --> PARSE{"File Format"}

    PARSE -->|KML| KML["KML Parser"]
    PARSE -->|ZIP| SHP["Shapefile ZIP Reader"]

    KML --> VAL["Dataset Validation"]
    SHP --> VAL

    VAL --> FEAT["Feature Extraction"]
    FEAT --> CRS["CRS-aware Measurements"]
    CRS --> PERSIST["SQLAlchemy Persistence"]

    PERSIST --> DB[("PostgreSQL / Supabase")]
    DB --> GET
    DB --> MEAS

    MEAS --> RESP["Feature Responses<br/>Geometry, CRS, Properties, Measurements"]
    RESP --> UI

    FEAT --> DISPLAY["Display Geometry Reprojection<br/>EPSG:4326"]
    DISPLAY --> RESP

    FH -.-> ERR["Validation / Processing Errors"]
    VAL -.-> ERR
    CRS -.-> ERR
    PERSIST -.-> ERR
    ERR --> UI
```

## 4. Installation and local setup (Windows)

```powershell
# 1. Clone and enter the repo
git clone https://github.com/ashishlukka1/geospatial-api.git
cd geospatial-api  # folder name on disk: aereo-2

# 2. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env (see §5) with your Supabase connection string
notepad .env
```

Verified with the commands in §13 using this layout (`app/`, `tests/`,
`sample_data/` at the repo root).

## 5. Environment configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes (server) | — | SQLAlchemy URL for Supabase PostgreSQL |
| `MAX_UPLOAD_BYTES` | no | `26214400` (25 MB) | Raw upload cap → HTTP 413 |
| `SHAPEFILE_MAX_UNCOMPRESSED_BYTES` | no | `104857600` (100 MB) | Declared + actual uncompressed ZIP cap → HTTP 413 |
| `SHAPEFILE_MAX_COMPRESSION_RATIO` | no | `200` | Rejects >200x ratios on entries over 1 MB → HTTP 413 |
| `MAX_FEATURES` | no | `20000` | Feature-count cap → HTTP 413 |
| `UPLOAD_DIR` | no | `<repo>/uploads` | Where raw uploads are staged; set to `/tmp/uploads` on Vercel (see §16) |
| `TESTING` | no | — | Set to `1` by `tests/conftest.py` only; skips PostgreSQL table creation |

Example `.env` (values are placeholders — never commit real credentials):

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/postgres
# Optional overrides:
# MAX_UPLOAD_BYTES=26214400
# SHAPEFILE_MAX_UNCOMPRESSED_BYTES=104857600
# SHAPEFILE_MAX_COMPRESSION_RATIO=200
# MAX_FEATURES=20000
```

Credential safety: `.env` is git-ignored and never printed by the app;
`app/db.py` raises at startup if `DATABASE_URL` is missing rather than
falling back to a default. API error bodies never include connection
strings, SQL, filesystem paths, or tracebacks (verified by
`test_error_bodies_hide_internals`).

## 6. Starting the application

```powershell
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

- Viewer: http://127.0.0.1:8000/
- Interactive docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health → `{"status": "healthy"}`
- If port 8000 is occupied, use `uvicorn app.main:app --port 8001 --reload`.
- Tables are created automatically on startup (`Base.metadata.create_all`).

## 7. API documentation

All routes use trailing slashes (`POST /api/files/`,
`GET /api/files/{id}/`, `GET /api/files/{id}/measurements/`).

### POST /api/files/

Multipart upload with a `file` field (`.kml` or `.zip`). Stores the bytes
under `uploads/<uuid>/`, parses, validates, measures, and persists
atomically, then returns the file record.

Success `200` (`FileResponse`): `id`, `filename`, `feature_count`,
`crs`, `status`.

Errors: `400` malformed/unsupported content (bad extension, empty file,
corrupt KML/ZIP, missing Shapefile components, bad geometry/CRS —
a blank multipart filename is rejected by the framework with `422`);
`413` over a configured size limit; `500` unexpected failure (generic
message only). Failures are recorded with status `FAILED` when possible.

### GET /api/files/{id}/

Returns the stored `FileResponse` for one upload. `404` with
`{"detail": "File not found."}` for unknown IDs.

### GET /api/files/{id}/measurements/

Returns `{"file_id": ..., "features": [...]}` ordered by `feature_index`.
Each feature carries `geometry_type`, source `geometry` (GeoJSON),
`display_geometry` (EPSG:4326 copy for the map), `crs`,
`projected_crs`, `properties`, and `measurement`
(`{"type": "area"|"length", "value", "unit"}` or `null`). Values are
rounded to two decimals in the response; the database keeps full precision.

## 8. Examples

Viewer screenshots of extracted file details (metadata, features table
and map visualization):

### KML upload (`mixed.kml`: Polygon + LineString + Point)

![KML extraction example](images/mixed.png)

### Point features from a zipped Shapefile (`State_Capitals.zip`, custom CRS)

![Shapefile point extraction example](images/points.png)

### Polygon features from a zipped Shapefile (`polygons.zip`)

![Shapefile polygon extraction example](images/shpfile.png)

## 9. Supported formats

- **KML** (`.kml`): read with the GeoPandas KML driver; coordinates are
  WGS84 by spec, stored as `EPSG:4326`. A single null-geometry Placemark
  among usable features is stored with nulls; datasets with no usable
  geometry are rejected.
- **Zipped Shapefile** (`.zip`): exactly one `.shp` with matching `.shx`
  and `.dbf` (same directory, same basename, case-insensitive), at the
  root or in a nested directory. `.prj` supplies the source CRS, which is
  preserved verbatim. macOS metadata (`__MACOSX/`, `._*`), hidden, and
  unrelated files are ignored and never extracted — only the layer's own
  sidecars (`.shp/.shx/.dbf/.prj/.cpg/.qix/.sbn/.sbx`) are written to a
  temporary directory that is always cleaned up. Multiple `.shp` files are
  rejected rather than guessed between.

## 10. File-processing pipeline

1. **Upload**: filename checked, body read in 64 KB chunks against
   `MAX_UPLOAD_BYTES`, saved under `uploads/<uuid>/` using only the
   filename's basename (path separators cannot escape).
2. **Record**: a `files` row is inserted with status `PROCESSING`.
3. **Parse**: KML via `parse_kml_file`, ZIP via `read_shapefile_zip`
   (validate → extract subset → `gpd.read_file`, all inside a
   `TemporaryDirectory`).
4. **Validate** (`validate_dataset`): non-empty, under the feature cap,
   CRS present and parseable, at least one usable geometry, all
   coordinates finite.
5. **Measure + extract**: per-feature UTM measurement, JSON-safe
   properties, GeoJSON mapping; source geometry untouched.
6. **Persist atomically**: features plus the `COMPLETED` status commit
   together (`complete_with_features`); any failure rolls back so no
   partial rows remain, and the file is marked `FAILED` on a fresh
   transaction.
7. **Visualize**: the viewer calls the three endpoints in order and
   renders `display_geometry` on Leaflet (blue polygons, orange lines,
   red points; click for properties + measurement), fitting the map to
   the geometries.

## 11. CRS handling and measurements

- Source CRS is stored verbatim in `TEXT` columns (`files.crs`,
  `features.crs`), including long custom WKT (e.g. a ~600-character
  Lambert Conformal Conic definition from an Indian dataset).
- KML defaults to `EPSG:4326`; Shapefiles must carry a readable CRS —
  missing/unparseable CRS is a `400`, never silently defaulted.
- Measurement (`measure.py`): points (and empty geometries) → null;
  Polygon/MultiPolygon → `area` in m²; LineString/MultiLineString → `length`
  in m; anything else (e.g. GeometryCollection) → null without crashing.
  The UTM zone is chosen from a WGS84 copy (`crs.py`, poles rejected),
  then geometry is reprojected from its true source CRS; transform
  failures surface as `400`, non-finite results become null.
- `display_geometry` is a server-side EPSG:4326 reprojection for Leaflet
  only; on failure the source geometry is returned with a logged warning.

## 12. Validation, limits, and transaction behavior

- Upload body, uncompressed size (checked before *and* during extraction),
  compression ratio, and feature count are capped (→ `413`); everything
  else malformed is `400`; unknown IDs are `404`.
- Archives: `is_zipfile` check (extension alone is never trusted),
  absolute/traversal paths rejected, duplicate entries rejected,
  companions and single-layer rule enforced before reading.
- Failed commits roll back before any status write; `mark_failed` itself
  rolls back first and never masks the original error with a second
  exception. Error details are scrubbed of filesystem paths and IDs.
- These are application-level guards, not complete DoS protection: pair
  with reverse-proxy request-size limits (e.g. nginx
  `client_max_body_size`) in production.

## 13. Tests and sample datasets

```powershell
.\venv\Scripts\Activate.ps1
.\venv\Scripts\python.exe -m pytest -q
```

82 tests, no external services: an in-memory SQLite database
(`tests/conftest.py`, `TESTING=1`) with synthetic fixtures generated by
GeoPandas — success paths (KML, root/nested/projected-CRS ZIPs),
14 failure modes, transaction atomicity, leak-free errors, CRS storage,
display reprojection, and homepage/static serving.

Sample datasets in `sample_data/`:

| File | Contents | Use |
|---|---|---|
| `sample.kml` | Point (Connaught Place) + Polygon (Test Zone), Delhi | basic KML upload |
| `mixed.kml` | Polygon + LineString + Point, Hyderabad | all geometry types + measurements |
| `polygons.zip` | two-polygon EPSG:4326 Shapefile | manual ZIP upload via the viewer |

To exercise a larger real-world file (e.g. the 34-point Indian
Lambert-Conformal-Conic dataset), obtain it from its publisher and
upload through the viewer or `/docs`; large sources are intentionally
not vendored (see §15).

## 14. Design decisions and trade-offs

- **One pipeline for both formats**: Shapefile support reuses extraction,
  measurement, persistence, and response code instead of a parallel
  implementation — smaller surface, one behavior to explain.
- **Whole-file rejection vs per-feature errors**: malformed data (bad CRS,
  NaN coordinates, empty sets) rejects the file with a clear `400`, while
  tolerable per-feature cases (null/empty geometry, points, unsupported
  types) persist with explicit nulls. Rationale: measurement and display
  require trustworthy inputs; nulls keep the contract honest.
- **No geometry repair**: invalid (self-intersecting) shapes are stored
  as-is with best-effort measurements, documented and tested — repair
  would silently change user data.
- **Single-commit persistence**: features + `COMPLETED` commit together
  so failures cannot strand partial rows; the trade-off is one larger
  transaction instead of incremental writes.
- **Server-side display reprojection** over client-side proj4: arbitrary
  WKT definitions stay parseable by pyproj without shipping CRS
  definitions to the browser.
- **Additive response evolution**: `display_geometry` was added alongside
  `geometry` so existing clients keep working.

## 15. Known limitations, learning outcomes, future scope

Limitations (honest): synchronous processing ties up a worker per large
upload (no job queue); ZIP-bomb defense is heuristic size/ratio caps;
request limits apply after ASGI buffering (needs proxy limits); no auth,
pagination, or rate limiting; SQLite-vs-PostgreSQL type differences mean
VARCHAR-length regressions need column-type assertions (as done in
`test_crs_storage.py`); blank multipart filenames are rejected by the
framework with `422` before application code runs.

Outcomes: CRS-aware measurement, content-based archive validation,
transaction-safe persistence, leak-free API errors, and a dependency-free
viewer were all implemented, tested (82 passing), and verified against a
live Supabase schema (CRS `TEXT` migration + 559-char round-trip).

Future scope (not started): background processing, paginated
measurements, upload quotas/auth, multi-layer ZIP selection, and
proxy/CDN deployment configuration.
