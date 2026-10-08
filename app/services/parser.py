"""KML parsing with GeoPandas."""

import geopandas as gpd


def parse_kml_file(path: str) -> gpd.GeoDataFrame:
    """Read a KML file and return its features as a GeoDataFrame.

    KML files always store coordinates in WGS84, so the result
    uses EPSG:4326. Raises ValueError if the file cannot be read.
    """
    try:
        gdf = gpd.read_file(path, driver="KML")
    except Exception as exc:
        raise ValueError(f"Could not parse KML file: {exc}") from exc
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    return gdf
