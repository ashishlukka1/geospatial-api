# Changelog

## Iteration 3

- Added measurement columns to `features` (type/value/unit, projected CRS).
- Added UTM selection (`app/services/crs.py`) and area/length
  measurement (`app/services/measure.py`).
- Uploads now measure every feature; points and unsupported types
  store nulls.
- Measurements endpoint returns nested `measurement` (2-decimal
  presentation, full precision in DB).
- Added 10 new tests (24 total passing).

- Added `features` table with one-to-many relationship to `files`.
- Added per-feature extraction (GeoJSON geometry, CRS, JSON-safe
  properties) in `app/services/features.py`.
- Uploads now persist every feature linked by `file_id`.
- Added `GET /api/files/{id}/measurements/` (measurement is null).
- Added `sample_data/mixed.kml` and 8 new tests (14 total passing).
- Moved shared test-database setup into `tests/conftest.py`.

- Added PostgreSQL connection (`app/db.py`) with `DATABASE_URL` from `.env`.
- Added `files` table with PROCESSING / COMPLETED / FAILED status
  (`app/models.py`).
- Added `POST /api/files/` KML upload endpoint.
- Added `GET /api/files/{id}/` file information endpoint.
- Added KML parsing service using GeoPandas (EPSG:4326, feature count).
- Added Pydantic `FileResponse` schema for both endpoints.
- Added `sample_data/sample.kml` and 6 passing tests.
- Added `psycopg2-binary`, `python-dotenv`, `pydantic`, `httpx`
  to `requirements.txt`.

## Iteration 0

- Initialized FastAPI project (`GET /`, `GET /health`, `/docs`).
