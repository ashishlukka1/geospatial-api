# Decisions

## PostgreSQL as the database (Iteration 1)

- Why PostgreSQL: the project stores relational file/feature records and
  will later need real geospatial queries; PostgreSQL (+ PostGIS path)
  is the standard for that, while SQLite was only fine for Iteration 0.
- Why cloud-hosted PostgreSQL: no local install to explain or maintain,
  and the assessment database stays available from anywhere.
- Why Supabase: free hosted PostgreSQL with a connection string ready
  to paste — no server setup for this iteration.
- Why the connection string lives in `.env`: the URL contains the
  database password. `.env` is listed in `.gitignore` and never
  committed, so the password cannot leak through git, logs, or API
  responses. Python reads it via `python-dotenv`; code only ever sees
  the variable name `DATABASE_URL`.

## No Alembic yet (Iteration 1)

One table, no migration history to preserve — `create_all()` on startup
is enough. Alembic will be introduced when schema changes need
versioned migrations.

## No features table yet (Iteration 1)

The goal is file metadata only. Per-geometry storage belongs with the
measurement work in a later iteration.

## Iteration 2 additions

- Generic SQLAlchemy `JSON` (not `JSONB`, not PostGIS) for geometry and
  properties: renders as `json` in PostgreSQL and still works on the
  SQLite throwaway test database, so tests stay portable. No new driver.
- Shapely `mapping()` for GeoJSON: the standard one-call conversion,
  guaranteed JSON serializable, no custom encoder to explain.
- `to_json_safe()` as a small recursive service function: GeoPandas
  hands us NumPy/NaN/pandas values that `json.dumps` and PostgreSQL
  JSON reject, so every property value passes through it before storage.
- Standard-library `logging` for the three progress lines: the project
  had no logging system, and adding a framework for three lines would
  violate the no-unnecessary-libraries rule. No `print()` statements.
- One shared test database in `tests/conftest.py`: separate in-memory
  DBs per module silently fought over the single `get_db` override.
- `measurement` typed `float | None`, always `None`: reserves the
  contract for Iteration 3 without calculating anything now.

## Iteration 3 additions

- Why UTM: degrees are not meters — longitude degrees shrink toward the
  poles, so measuring in EPSG:4326 is meaningless. UTM projects a narrow
  6° slice onto a flat meter grid where plain area/length is correct.
- Why `representative_point()`: guaranteed inside the geometry, while
  `centroid()` can fall outside concave shapes and pick the wrong zone.
- Why the source stays EPSG:4326: transparency and reproducibility — the
  stored geometry is what the user uploaded; `projected_crs` records how
  the number was derived so anyone can recompute it.
- Why points have no measurement: a point has zero area and length by
  definition; nulls (not zeros) distinguish "not applicable" from a
  real zero measurement.
- Why round only the response: the DB keeps full float precision for
  future math; the API shows 2 decimals because nobody reads 14 digits.
- Manual `ALTER TABLE` this once: `create_all()` cannot add columns to
  an existing table, which is exactly the pain Alembic will solve later.
- Known limits kept small on purpose: poles rejected with a clear error
  (|lat| > 84, UTM undefined there), antimeridian documented as an edge
  case, no polar/antimeridian framework built yet.
