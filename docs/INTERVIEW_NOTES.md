# Interview Notes — Iteration 3

## Why degrees cannot be measured directly

One degree of longitude is ~111 km at the equator but ~0 km at the
poles. EPSG:4326 coordinates are angles, not meters, so area/length
must be computed after projecting onto a flat meter grid.

## How the UTM zone is calculated

Take a point inside the feature, read lon/lat, then
`zone = floor((lon + 180) / 6) + 1`. Northern hemisphere →
`32600 + zone`, southern → `32700 + zone`. Hyderabad (78.47°E) gives
zone 44 → EPSG:32644; Sydney (151.21°E, 33.87°S) gives zone 56 →
EPSG:32756.

## Why representative_point() is used

The zone must come from a point actually on the feature. `centroid()`
of a concave polygon can lie outside it (even in another zone);
`representative_point()` is guaranteed inside, so the zone is always
correct for the feature.

## The measurement pipeline

WGS84 geometry → `choose_utm_crs()` → `GeoSeries.to_crs()` reproject
(CRS-aware, never manual math) → Shapely `.area`/`.length` on the
meter grid. Polygon/MultiPolygon → area in m²; LineString/
MultiLineString → length in m; points and unknown types → nulls.

## Why the source geometry remains EPSG:4326

The database stores what the user uploaded. `projected_crs` is
metadata explaining the derivation — anyone can reproject the stored
GeoJSON with the stored CRS and reproduce the number.

## Supported types and limits

Measured: Polygon, MultiPolygon, LineString, MultiLineString.
Null (by design): Point, MultiPoint, anything else — never a crash.
Rejected with a message: |lat| > 84 (UTM undefined). Edge case on
record: antimeridian-crossing shapes use their representative point's
zone.

---

# Interview Notes — Iteration 2

## The features table

One row per geometry: UUID `id`, `file_id` foreign key to `files.id`,
`feature_index` (position in the file), `geometry_type` (e.g. Polygon),
`geometry` (GeoJSON dict), `crs` string, `properties` (JSON dict).
`FileRecord.features` / `FeatureRecord.file` form the one-to-many
relationship; deleting a file deletes its features (cascade).

## How extraction works

After `parse_kml_file()` returns a GeoDataFrame, `extract_features()`
loops rows with `enumerate`: index = position, `geom.geom_type` = type,
Shapely `mapping(geom)` = `{"type": ..., "coordinates": ...}` dict,
properties = every column except the geometry column, each passed
through `to_json_safe()`. `save_features()` turns the dicts into
`FeatureRecord` rows with fresh UUIDs and commits once.

## Why properties need conversion

GeoPandas values are NumPy/pandas types (`int64`, `NaN`, `NaT`,
timestamps) that break `json.dumps` and PostgreSQL JSON. `to_json_safe`
maps them to plain Python (`int`, `None`, ISO strings) recursively,
so storage and FastAPI responses never hit serialization errors.

## Why the endpoint reads the database

`GET .../measurements/` queries `features` by `file_id`, ordered by
`feature_index`. Reparsing the KML per request would waste time and
could return different results than what was stored; the DB is the
source of truth.

## Why measurement is null

The endpoint name reserves the final API contract, but area/length
needs UTM reprojection first (Iteration 3). Returning `null` now is
honest: the field exists, the values are not computed yet.

---

# Interview Notes — Iteration 1

## How the database connection works

1. `app/db.py` calls `load_dotenv()`, which reads the local `.env` file
   into environment variables.
2. It reads `DATABASE_URL` from the environment — the password lives only
   in `.env`, never in Python code.
3. It builds one SQLAlchemy engine from that URL. The engine holds a pool
   of real database connections.
4. On startup, `app/main.py` runs `Base.metadata.create_all(bind=engine)`,
   which creates the `files` table if it does not exist yet.

## Why SQLAlchemy is used

Raw SQL strings are error-prone and tie us to one database. SQLAlchemy
lets us define tables as Python classes, build queries in Python, and
switch databases (PostgreSQL vs SQLite in tests) by changing only the URL.

## What the engine does

The engine owns the connection pool. It opens physical connections to
PostgreSQL, lends them to sessions, and reuses them afterwards instead
of reconnecting for every request.

## What a database session is

A Session is one request's workspace: objects you `add()` are staged,
`commit()` writes them to the database, and `close()` returns the
connection to the pool. Each request gets a fresh session so requests
never share half-written state.

## How FastAPI receives the session

Through dependency injection: route functions declare
`db: Session = Depends(get_db)`. FastAPI calls `get_db()` before the
route, passes the yielded session in, and runs the cleanup code
(`db.close()`) after the response is sent.

## Upload flow (POST /api/files/)

1. FastAPI receives the multipart file and gives the route an `UploadFile`.
2. The route reads the bytes and calls
   `file_handler.validate_upload()` → HTTP 400 for bad extension/empty.
3. A UUID is generated; bytes are saved to `uploads/<uuid>/<filename>`.
4. A `files` row is inserted with status PROCESSING.
5. `parser.parse_kml_file()` reads the saved file with GeoPandas.
6. Success → row becomes COMPLETED with feature_count and EPSG:4326.
   Failure → row becomes FAILED with a short message, client gets
   HTTP 400 with that message (never a traceback).
7. The row is returned through the `FileResponse` Pydantic model.

## KML parsing flow

`gpd.read_file(path, driver="KML")` → GeoDataFrame. KML coordinates are
always WGS84, so if no CRS is attached we set EPSG:4326 explicitly.
`len(gdf)` is the feature count. Any read error is wrapped in a
`ValueError` with a one-line message.

## Why routes are kept thin

Routes handle HTTP only (input, status codes, response shape). All
decisions — validation rules, file paths, record updates — live in
services, so they can be tested and reused without HTTP.
