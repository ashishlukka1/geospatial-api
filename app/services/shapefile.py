"""Zipped Shapefile validation, extraction, and reading.

Reuses the existing feature pipeline: this module only produces a
GeoDataFrame with its real source CRS. Measurement, persistence, and
response building stay in the existing services.

Security model (small and auditable):
- Member paths are validated before anything is written; absolute
  paths and `..` traversal are rejected.
- Duplicate archive entries are rejected rather than silently
  overwritten.
- Declared uncompressed sizes are summed before extraction, actual
  written bytes are capped during extraction, and absurd compression
  ratios are rejected up front.
- Only the selected layer's own files (same directory, same basename)
  are extracted; unrelated, hidden, and macOS metadata files are
  never written to disk.
- Extraction lives inside a TemporaryDirectory removed on exit.
"""

import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import geopandas as gpd

from app.services.file_handler import PayloadTooLargeError

MAX_UNCOMPRESSED_SIZE = int(os.getenv("SHAPEFILE_MAX_UNCOMPRESSED_BYTES", str(100 * 1024 * 1024)))
# Declared-size / compressed-size above this is treated as a likely
# ZIP bomb (e.g. 5 MB of zeros compressing to ~5 KB is ratio ~1000).
MAX_COMPRESSION_RATIO = float(os.getenv("SHAPEFILE_MAX_COMPRESSION_RATIO", "200"))

# Sidecar extensions extracted alongside the selected layer. The .shp,
# .shx, and .dbf are required; the rest are optional helpers (.prj
# carries the CRS, .cpg the encoding).
_LAYER_EXTENSIONS = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".sbn", ".sbx"}


def _is_macos_metadata(name: str) -> bool:
    """Ignore __MACOSX/ entries and ._* AppleDouble files."""
    parts = PurePosixPath(name).parts
    if any(part == "__MACOSX" for part in parts):
        return True
    return PurePosixPath(name).name.startswith("._")


def _is_hidden_or_irrelevant(name: str) -> bool:
    """Unrelated files that are never candidates and never extracted."""
    base = PurePosixPath(name).name
    return base.startswith(".") or base.lower() in {"thumbs.db", "desktop.ini"}


def _is_unsafe_member(name: str) -> bool:
    """Detect absolute paths and path-traversal entries."""
    if not name or name.strip() == "":
        return True
    # Absolute POSIX or Windows paths (C:\, C:/, \\server).
    if name.startswith(("/", "\\")):
        return True
    if len(name) >= 3 and name[1] == ":" and name[0].isalpha():
        return True
    if name.startswith("\\\\"):
        return True
    parts = PurePosixPath(name.replace("\\", "/")).parts
    return any(part == ".." for part in parts)


def _safe_join(base: Path, member: str) -> Path:
    """Join a ZIP member onto base, ensuring it stays inside base."""
    target = (base / member).resolve()
    base_resolved = base.resolve()
    try:
        target.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"Unsafe archive path: {member}")
    return target


def _candidate_layer_names(members: list[zipfile.ZipInfo]) -> list[str]:
    """Return archive names of real .shp files, ignoring metadata."""
    return [
        info.filename
        for info in members
        if not info.is_dir()
        and not _is_macos_metadata(info.filename)
        and PurePosixPath(info.filename).suffix.lower() == ".shp"
        and not PurePosixPath(info.filename).name.startswith("._")
    ]


def read_shapefile_zip(zip_path: str) -> gpd.GeoDataFrame:
    """Validate, safely extract, and read a zipped Shapefile.

    The returned GeoDataFrame is fully in memory, so temporary files
    are removed before return on both success and failure. Raises
    ValueError (HTTP 400) for malformed content and
    PayloadTooLargeError (HTTP 413) for oversized archives.
    """
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Uploaded file is not a valid ZIP archive.")
    try:
        with zipfile.ZipFile(zip_path) as probe:
            members = probe.infolist()
    except zipfile.BadZipFile:
        raise ValueError("Uploaded file is not a valid ZIP archive.")

    files = [info for info in members if not info.is_dir()]
    if not files:
        raise ValueError("Archive contains no .shp file.")

    # Path safety + duplicate detection before touching disk.
    seen: set[str] = set()
    total_size = 0
    for info in files:
        name = info.filename
        if _is_unsafe_member(name):
            raise ValueError(f"Unsafe archive path: {name}")
        normalized = PurePosixPath(name.replace("\\", "/")).as_posix().lower()
        if normalized in seen:
            raise ValueError(f"Duplicate archive entry: {info.filename}")
        seen.add(normalized)
        if not _is_macos_metadata(name):
            total_size += info.file_size
            if total_size > MAX_UNCOMPRESSED_SIZE:
                raise PayloadTooLargeError(
                    f"Archive exceeds the {MAX_UNCOMPRESSED_SIZE}-byte uncompressed-size limit."
                )
            if info.compress_size > 0 and info.file_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_COMPRESSION_RATIO and info.file_size > 1024 * 1024:
                    raise PayloadTooLargeError(
                        "Archive has a suspicious compression ratio and was rejected."
                    )

    candidates = _candidate_layer_names(members)
    if len(candidates) == 0:
        raise ValueError("Archive contains no .shp file.")
    if len(candidates) > 1:
        raise ValueError(
            "Archive must contain exactly one .shp file; "
            f"found {len(candidates)}. Split layers into separate uploads."
        )

    layer_name = candidates[0]
    layer_posix = PurePosixPath(layer_name.replace("\\", "/"))
    layer_dir = layer_posix.parent
    layer_stem = layer_posix.stem.lower()

    # Companion files must share the layer's directory and basename.
    by_dir_stem: set[str] = set()
    for info in files:
        if _is_macos_metadata(info.filename):
            continue
        posix = PurePosixPath(info.filename.replace("\\", "/"))
        if posix.parent == layer_dir and posix.stem.lower() == layer_stem:
            by_dir_stem.add(posix.suffix.lower())
    for ext in (".shx", ".dbf"):
        if ext not in by_dir_stem:
            raise ValueError(f"Shapefile is missing its {ext} companion file.")

    # Extract only the layer's own files; skip everything unrelated.
    wanted = {
        info.filename
        for info in files
        if not _is_macos_metadata(info.filename)
        and PurePosixPath(info.filename.replace("\\", "/")).parent == layer_dir
        and PurePosixPath(info.filename.replace("\\", "/")).stem.lower() == layer_stem
        and PurePosixPath(info.filename.replace("\\", "/")).suffix.lower() in _LAYER_EXTENSIONS
    }

    with tempfile.TemporaryDirectory(prefix="shp_") as tmpdir:
        tmp = Path(tmpdir)
        written = 0
        with zipfile.ZipFile(zip_path) as archive:
            for info in files:
                if info.filename not in wanted:
                    continue
                target = _safe_join(tmp, info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, open(target, "wb") as dest:
                    while True:
                        chunk = source.read(64 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > MAX_UNCOMPRESSED_SIZE:
                            raise PayloadTooLargeError(
                                f"Archive exceeds the {MAX_UNCOMPRESSED_SIZE}-byte uncompressed-size limit."
                            )
                        dest.write(chunk)

        shp_paths = [
            p
            for p in tmp.rglob("*")
            if p.is_file() and p.suffix.lower() == ".shp"
        ]
        if len(shp_paths) != 1:
            raise ValueError("Archive must contain exactly one .shp file.")
        try:
            gdf = gpd.read_file(shp_paths[0])
        except Exception as exc:
            raise ValueError("Could not read Shapefile.") from exc
        if gdf.crs is None:
            raise ValueError("Shapefile CRS is missing or unknown.")
        try:
            _ = gdf.crs.to_epsg() or str(gdf.crs)
        except Exception:
            raise ValueError("Shapefile CRS is missing or unknown.")
        return gdf
