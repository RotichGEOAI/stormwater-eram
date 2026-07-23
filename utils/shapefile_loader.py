"""
Loads Kenya administrative-boundary shapefiles from the server-side
data/shapefiles/ folder (see that folder's README) into GeoDataFrames,
supports County -> Constituency -> Ward cascading selection by attribute
(mirroring "select by attribute" cascades in desktop GIS), and provides
zoom-to-ward bounds plus a synthetic zone grid clipped to the real ward
polygon so the flood/cost-benefit pipeline runs inside the actual boundary.
"""

from __future__ import annotations
import re
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from . import landcover_proxy, soil_hydrology, pollutant_loading

SHAPEFILE_DIR = Path(__file__).resolve().parent.parent / "data" / "shapefiles"

COUNTY_HINTS = ["county", "county_nam", "countyname", "adm1", "adm1_name", "name_1"]
CONSTITUENCY_HINTS = ["constituency", "const_name", "constituen", "adm2", "adm2_name",
                      "subcounty", "sub_county", "name_2"]
WARD_HINTS = ["ward", "ward_name", "wardname", "ward_nam", "adm3", "adm3_name", "name_3"]


class ShapefileLoadError(Exception):
    pass


# ----------------------------------------------------------------------
# Discovery + loading
# ----------------------------------------------------------------------
def list_available_shapefiles(base_dir: Path = SHAPEFILE_DIR) -> list[dict]:
    """
    Scan data/shapefiles/ (and one level of subfolders) for loadable
    bundles: standalone .zip files, or .shp files with sibling parts.
    Returns [{"label": display name, "path": Path to .shp or .zip}, ...]
    """
    base_dir = Path(base_dir)
    if not base_dir.exists():
        return []

    found = []
    seen_stems = set()
    for path in sorted(base_dir.rglob("*")):
        if path.is_dir():
            continue
        suffix = path.suffix.lower()
        rel = path.relative_to(base_dir)
        if suffix == ".zip":
            found.append({"label": str(rel), "path": path})
        elif suffix == ".shp":
            key = str(path.with_suffix(""))
            if key not in seen_stems:
                seen_stems.add(key)
                found.append({"label": str(rel), "path": path})
    return found


def load_shapefile_from_path(path: Path) -> gpd.GeoDataFrame:
    """Read a .shp (with sibling parts already on disk) or a .zip bundle into a WGS84 GeoDataFrame."""
    path = Path(path)
    try:
        if path.suffix.lower() == ".zip":
            gdf = gpd.read_file(f"zip://{path}")
        else:
            gdf = gpd.read_file(path)
    except Exception as exc:  # noqa: BLE001
        raise ShapefileLoadError(f"Failed to read shapefile at {path.name}: {exc}") from exc

    if gdf.empty:
        raise ShapefileLoadError(f"{path.name} has no features.")

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


# ----------------------------------------------------------------------
# Column guessing (County / Constituency / Ward)
# ----------------------------------------------------------------------
def _guess_column(gdf: gpd.GeoDataFrame, hints: list[str]) -> str | None:
    text_cols = [c for c in gdf.columns
                 if c != "geometry" and (gdf[c].dtype == object or pd.api.types.is_string_dtype(gdf[c]))]
    if not text_cols:
        return None
    # 1) exact, case-insensitive match — catches hints with digits/underscores (e.g. "name_1")
    #    that the normalized comparison below would otherwise never match, since it strips
    #    digits from the column name but not from the hint.
    for hint in hints:
        for col in text_cols:
            if hint == col.lower():
                return col
    # 2) normalized equality — letters only, so "COUNTY_NAM" matches "county_nam" etc.
    for hint in hints:
        for col in text_cols:
            if hint == re.sub(r"[^a-z]", "", col.lower()):
                return col
    # 3) substring — loosest match, last resort
    for hint in hints:
        for col in text_cols:
            if hint in col.lower():
                return col
    return text_cols[0]


def guess_county_column(gdf: gpd.GeoDataFrame) -> str | None:
    return _guess_column(gdf, COUNTY_HINTS)


def guess_constituency_column(gdf: gpd.GeoDataFrame) -> str | None:
    return _guess_column(gdf, CONSTITUENCY_HINTS)


def guess_ward_column(gdf: gpd.GeoDataFrame) -> str | None:
    return _guess_column(gdf, WARD_HINTS)


# ----------------------------------------------------------------------
# Cascading selection: County -> Constituency -> Ward
# ----------------------------------------------------------------------
def list_values(gdf: gpd.GeoDataFrame, col: str, filters: dict | None = None) -> list[str]:
    """
    Unique sorted values in `col`, optionally filtered by one or more
    {other_col: value} constraints (e.g. filter Constituency options down
    to the selected County).
    """
    d = gdf
    if filters:
        for f_col, f_val in filters.items():
            if f_col and f_val is not None:
                d = d[d[f_col] == f_val]
    return sorted(d[col].dropna().astype(str).unique().tolist())


def ward_bounds(gdf: gpd.GeoDataFrame, ward_col: str, ward_value: str, filters: dict | None = None):
    """Return (miny, minx, maxy, maxx) and (centroid_lat, centroid_lon) for one ward."""
    d = gdf
    if filters:
        for f_col, f_val in filters.items():
            if f_col and f_val is not None:
                d = d[d[f_col] == f_val]
    feature = d[d[ward_col] == ward_value]
    if feature.empty:
        raise ShapefileLoadError(f"No feature found for {ward_col} = {ward_value!r}.")
    minx, miny, maxx, maxy = feature.total_bounds
    centroid = feature.geometry.union_all().centroid
    return (miny, minx, maxy, maxx), (centroid.y, centroid.x)


# ----------------------------------------------------------------------
# Synthetic zone grid clipped to the real ward polygon
# ----------------------------------------------------------------------
def generate_zones_within_ward(gdf: gpd.GeoDataFrame, ward_col: str, ward_value: str,
                                filters: dict | None = None, zones_per_ward: int = 9,
                                seed: int = 7) -> pd.DataFrame:
    """
    Tile a grid of synthetic attribute zones clipped to the *actual*
    ward polygon from the shapefile, so downstream flood/cost-benefit
    models run against a real boundary instead of the built-in sample grid.
    """
    d = gdf
    if filters:
        for f_col, f_val in filters.items():
            if f_col and f_val is not None:
                d = d[d[f_col] == f_val]
    feature = d[d[ward_col] == ward_value]
    if feature.empty:
        raise ShapefileLoadError(f"No feature found for {ward_col} = {ward_value!r}.")
    ward_poly = feature.geometry.union_all()

    minx, miny, maxx, maxy = ward_poly.bounds
    rng = np.random.default_rng(seed)
    land_uses = ["Residential", "Commercial", "Industrial", "Agricultural"]

    cols = max(3, int(np.ceil(np.sqrt(zones_per_ward * 3))))  # oversample the bbox, then keep what's inside
    xs = np.linspace(minx, maxx, cols + 1)
    ys = np.linspace(miny, maxy, cols + 1)

    rows = []
    z_i = 0
    for i in range(cols):
        for j in range(cols):
            if z_i >= zones_per_ward:
                break
            cell = Polygon([
                (xs[i], ys[j]), (xs[i + 1], ys[j]),
                (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1]),
            ])
            clipped = cell.intersection(ward_poly)
            if clipped.is_empty or clipped.area <= 0:
                continue
            centroid = clipped.centroid
            land_use = land_uses[z_i % len(land_uses)]
            zone_seed = seed * 1000 + z_i
            landcover = landcover_proxy.sample_landcover(land_use, seed=zone_seed)
            impervious = landcover_proxy.estimate_imperviousness(landcover, seed=zone_seed)
            hsg = soil_hydrology.assign_hsg_proxy(land_use, seed=zone_seed)
            point_source = pollutant_loading.has_point_source(land_use, seed=zone_seed)
            population = int(rng.uniform(800, 6000)) if land_use != "Agricultural" else int(rng.uniform(100, 900))
            rows.append({
                "Ward": ward_value,
                "Zone": f"{str(ward_value)[:12]}-Z{z_i + 1}",
                "LandUse": land_use,
                "LandCover": landcover,
                "ImperviousSurface": round(impervious, 1),
                "HSG": hsg,
                "PointSource": point_source,
                "Population": population,
                "MeanRainfall_mm": round(float(rng.uniform(60, 130)), 1),
                "geometry": clipped,
                "lat": centroid.y,
                "lon": centroid.x,
            })
            z_i += 1
        if z_i >= zones_per_ward:
            break

    if not rows:
        raise ShapefileLoadError(
            "Couldn't fit any zones inside that ward's geometry — polygon may be too small/complex.")
    return pd.DataFrame(rows)
