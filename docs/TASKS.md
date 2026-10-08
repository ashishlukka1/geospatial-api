# Tasks — Iteration 1: PostgreSQL + KML upload + file metadata API

- [x] PostgreSQL connection via `app/db.py` (engine, session factory, `get_db`)
- [x] `files` table via `app/models.py` (UUID id, filename, status enum, feature_count, crs, error_message, created_at)
- [x] Tables auto-created on application startup (no Alembic yet)
- [x] `.env` support with `DATABASE_URL` (never committed)
- [x] `uploads/<uuid>/` storage (path built from UUID, not user filename)
- [x] `POST /api/files/` — accepts `.kml`, 400 on bad extension / empty file
- [x] KML parsing service with GeoPandas (`app/services/parser.py`, EPSG:4326, feature count)
- [x] PROCESSING → COMPLETED / FAILED status handling (no raw tracebacks)
- [x] `GET /api/files/{id}/` — file info, 404 on unknown ID
- [x] Pydantic response schemas (`app/schemas.py`)
- [x] 6 tests in `tests/test_files.py` (all passing)
- [x] Live verification against Supabase (via pooler string, port 6543)

Not started (later iterations):

- [ ] Shapefile ZIP support
- [ ] Features table
- [ ] Area / length measurement, UTM, CRS transformation
- [ ] Background processing, auth, pagination, Docker

# Tasks — Iteration 2: Feature Extraction

- [x] `features` table (`FeatureRecord`: UUID id, `file_id` FK, feature_index, geometry_type, geometry JSON, crs, properties JSON)
- [x] One-to-many files → features relationship (with delete cascade)
- [x] Per-feature extraction service (`app/services/features.py`, route stays thin)
- [x] Geometry stored as GeoJSON dicts via Shapely `mapping()`
- [x] Properties = all non-geometry columns, JSON-safe conversion (NaN/NumPy/datetime)
- [x] Features persisted on upload, linked by `file_id`
- [x] Pydantic `FeatureResponse` / `MeasurementsResponse` (`measurement` always null)
- [x] `GET /api/files/{id}/measurements/` reads stored rows (never reparses KML)
- [x] `sample_data/mixed.kml` (Polygon + LineString + Point)
- [x] 8 new tests in `tests/test_measurements.py`, shared `tests/conftest.py`
- [x] Live verification against Supabase + docs updated

# Tasks — Iteration 3: Measurements and CRS

- [x] Measurement columns on `features` (measurement_type/value/unit, projected_crs, all nullable)
- [x] UTM selection service (`app/services/crs.py`, `choose_utm_crs`, representative point, poles rejected)
- [x] Measurement service (`app/services/measure.py`, GeoPandas reprojection, area/length, points + unsupported → null)
- [x] Source geometry/CRS stored unchanged; projected CRS kept as metadata
- [x] Nested `measurement` in API response, value rounded to 2 decimals (DB keeps full precision)
- [x] Per-feature pipeline logs (no geometries, no prints)
- [x] UTM unit tests (Hyderabad 32644, Sydney 32756, zone boundary)
- [x] Known-answer tests (1 km square ≈ 1,000,000 m², 1 km line, multi-types, unsupported)
- [x] Full integration test (mixed.kml → COMPLETED → measurements)
- [x] `mixed.kml` moved to Hyderabad (UTM 44N)
- [x] Live verification + Supabase SQL check + docs updated
