# Progress — Iteration 2

## Iteration

2 — Feature extraction: KML → GeoPandas → per-feature rows in a
`features` table → `GET /api/files/{id}/measurements/`.

## What was implemented

- `features` table (`FeatureRecord` in `app/models.py`): UUID string id,
  `file_id` foreign key to `files.id`, feature_index, geometry_type,
  geometry (generic SQLAlchemy JSON → `json` in PostgreSQL),
  crs string, properties (JSON). One-to-many relationship with
  `FileRecord.features` and cascade delete.
- `app/services/features.py`: `to_json_safe()` (NaN/NA/NaT → None,
  NumPy int/float/bool → Python types, datetime → ISO string, nested
  dicts/lists handled recursively), `extract_features()` (index,
  Shapely `mapping()` GeoJSON, CRS, non-geometry properties per row),
  `save_features()` (one `FeatureRecord` per dict, single commit).
  Standard-library logging only: extracting / extracted / stored lines,
  never full geometries.
- Upload flow extended (route still thin): after parsing, extract +
  save features inside the existing try block; any unexpected failure
  marks the file FAILED and returns HTTP 500 with a generic message
  (no traceback leak). `feature_count`/`status` behavior unchanged.
- `GET /api/files/{id}/measurements/` returns stored rows ordered by
  feature_index with `measurement: null` for every feature (Iteration 3
  work). 404 for unknown IDs. The KML is never reparsed here.
- `sample_data/mixed.kml`: Polygon (Campus) + LineString (Main Path) +
  nameless Point (exercises null properties).
- Tests: `tests/conftest.py` now owns the single shared throwaway
  database (two test modules previously created two in-memory DBs that
  fought over one `get_db` override — that broke one Iteration 1 test
  until fixed). `tests/test_measurements.py` adds 8 tests: upload,
  count = 3, geometry types, DB persistence, endpoint shape,
  404, `to_json_safe` unit checks, null-property integration.

## Files created / changed

- Created: `app/services/features.py`, `sample_data/mixed.kml`,
  `tests/conftest.py`, `tests/test_measurements.py`
- Changed: `app/models.py` (FeatureRecord + relationship),
  `app/schemas.py` (FeatureResponse, MeasurementsResponse),
  `app/api/files.py` (persist on upload + measurements endpoint),
  `tests/test_files.py` (uses shared fixtures, assertions unchanged),
  docs (all five)
- No new libraries: numpy/pandas come with GeoPandas.

## Verification performed

- `python -m pytest tests/ -v` → 14 passed (6 old + 8 new).
- Live server vs Supabase: `mixed.kml` upload → COMPLETED, count 3;
  measurements endpoint returns Polygon/LineString/Point with
  EPSG:4326, real properties, `measurement: null`; unknown ID → 404.
- Supabase SQL: `features` holds the 3 rows; `pg_typeof` confirms
  `json`/`json` columns; stored geometry has GeoJSON type/coordinates.
- Note: a stale process was squatting on port 8000 serving Iteration 1
  code, so live verification ran on port 8001. Iteration 1 behavior
  on 8000 is unaffected.

## Known issues

- None for this iteration. Measurements are intentionally null.

---

# Progress — Iteration 1

## Iteration

1 — PostgreSQL database setup + basic KML upload + file metadata API.

## What was implemented

- PostgreSQL connection (`app/db.py`): reads `DATABASE_URL` from `.env`,
  creates one SQLAlchemy engine, one session factory, and a `get_db`
  dependency that opens a session per request and closes it afterwards.
- `files` table (`app/models.py`): UUID string id, filename, `FileStatus`
  enum (PROCESSING / COMPLETED / FAILED), feature_count, crs,
  error_message, created_at. No features table yet.
- Tables are created automatically on startup via
  `Base.metadata.create_all(bind=engine)` in `app/main.py`. No Alembic:
  one table and no migration history make it unnecessary for now.
- `POST /api/files/`: validates `.kml` extension and non-empty content
  (HTTP 400 otherwise), generates a UUID, saves bytes to
  `uploads/<uuid>/<filename>`, inserts a PROCESSING row, parses the KML
  with GeoPandas, then marks the row COMPLETED (feature_count, EPSG:4326)
  or FAILED (short error message, no traceback).
- `GET /api/files/{id}/`: returns id, filename, feature_count, crs,
  status; HTTP 404 for unknown IDs.
- Pydantic `FileResponse` schema (`app/schemas.py`) used for both
  endpoints instead of raw dicts.
- Thin routes (`app/api/files.py`), business logic in
  `app/services/file_handler.py` and `app/services/parser.py`.
- `sample_data/sample.kml`: 1 point + 1 polygon around Delhi (2 features).
- `tests/test_files.py`: 6 tests, all passing (throwaway in-memory
  SQLite, real database untouched).

## Files created / changed

- Created: `app/db.py`, `app/models.py`, `app/schemas.py`,
  `app/api/files.py`, `app/services/file_handler.py`,
  `app/services/parser.py`, `sample_data/sample.kml`,
  `tests/test_files.py`, `.env` (gitignored),
  `docs/TASKS.md`, `docs/PROGRESS.md`, `docs/CHANGELOG.md`,
  `docs/INTERVIEW_NOTES.md`, `docs/DECISIONS.md`, `uploads/`
- Changed: `app/main.py` (router + table creation),
  `requirements.txt` (added `psycopg2-binary`, `python-dotenv`,
  `pydantic`, `httpx`)
- Added one explained library: `httpx` (transport used by FastAPI's
  TestClient in tests).

## Verification performed

- `python -m pytest tests/ -v` → 6 passed.
- GeoPandas KML check: `sample.kml` reads as 2 features, CRS EPSG:4326.
- Live verification against Supabase (pooler, port 6543): server started,
  `POST /api/files/` with `sample.kml` → COMPLETED with 2 features and
  EPSG:4326, invalid extension → HTTP 400, `GET` by ID → same record,
  unknown ID → HTTP 404, and the `files` table contains the matching row.

## Known issues

- The direct database host on port 5432 is unreachable from this machine
  (TCP timeout), so `.env` uses the Supabase pooler string
  (`aws-0-...pooler.supabase.com:6543`) instead. No code change was needed:
  only `DATABASE_URL` changed.
