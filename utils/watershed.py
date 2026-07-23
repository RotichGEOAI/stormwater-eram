"""
Indicative watershed/catchment and riparian-buffer analysis for Kenya.

There is no live hydrology API wired in here (no Water Resources Authority
Kenya or HydroSHEDS/HydroRIVERS feed reachable from this environment), so
this module ships a small, clearly-labeled set of major Kenyan rivers as
simplified polylines (a handful of real, approximate vertices along each
river's course -- enough to show which drainage basin a ward sits in and
to compute a riparian buffer, but NOT survey-grade hydrography). Replace
`MAJOR_RIVERS` with a real HydroRIVERS/WRA Kenya rivers shapefile for
production use -- everything downstream (basin assignment, buffering,
carbon-priority scoring) takes any GeoDataFrame of river lines unchanged.

Basins represented (drainage systems relevant to the app's North Rift /
Lake Victoria basin sample wards, plus the two major national basins for
context): Nzoia, Yala, Nyando, Sondu-Miriu, Kerio-Turkwel (Lake Victoria /
Lake Turkana basins), Athi, and Tana (national reference rivers).
"""

from __future__ import annotations
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

# Approximate courses (a handful of vertices each) -- indicative only.
MAJOR_RIVERS = {
    "Nzoia": {"basin": "Lake Victoria Basin",
              "coords": [(35.35, 0.85), (35.10, 0.60), (34.85, 0.45), (34.45, 0.15), (34.15, 0.05)]},
    "Yala": {"basin": "Lake Victoria Basin",
             "coords": [(35.25, 0.40), (35.00, 0.20), (34.70, 0.05), (34.30, -0.05)]},
    "Nyando": {"basin": "Lake Victoria Basin",
               "coords": [(35.40, 0.10), (35.15, -0.05), (34.90, -0.10), (34.70, -0.15)]},
    "Sondu-Miriu": {"basin": "Lake Victoria Basin",
                    "coords": [(35.35, -0.35), (35.10, -0.35), (34.75, -0.35), (34.55, -0.40)]},
    "Kerio": {"basin": "Lake Turkana Basin",
              "coords": [(35.55, 1.10), (35.75, 1.60), (35.95, 2.20), (36.05, 2.80)]},
    "Turkwel": {"basin": "Lake Turkana Basin",
                "coords": [(34.90, 1.40), (35.20, 1.90), (35.50, 2.50), (35.75, 3.10)]},
    "Athi-Galana": {"basin": "Athi Basin",
                    "coords": [(37.00, -1.30), (37.60, -2.30), (38.50, -3.10), (39.60, -3.40)]},
    "Tana": {"basin": "Tana Basin",
             "coords": [(37.10, -0.35), (37.80, -0.55), (38.80, -1.10), (39.90, -2.50)]},
}

# Riparian conservation buffer widths (meters). Kenya's Water Resources
# (Riparian) rules set a default of 30m for smaller watercourses, scaling
# up for larger rivers -- we key a coarse "large/medium" flag off the
# river dict rather than a discharge dataset we don't have.
DEFAULT_RIPARIAN_BUFFER_M = 30
LARGE_RIVER_BUFFER_M = 100
LARGE_RIVERS = {"Tana", "Athi-Galana", "Nzoia"}


def rivers_geodataframe() -> gpd.GeoDataFrame:
    """Build the indicative rivers GeoDataFrame (WGS84 lines + basin name)."""
    rows = []
    for name, info in MAJOR_RIVERS.items():
        rows.append({"River": name, "Basin": info["basin"], "geometry": LineString(info["coords"])})
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def _buffer_width_m(river_name: str) -> int:
    return LARGE_RIVER_BUFFER_M if river_name in LARGE_RIVERS else DEFAULT_RIPARIAN_BUFFER_M


def riparian_buffers(rivers_gdf: gpd.GeoDataFrame | None = None) -> gpd.GeoDataFrame:
    """Buffer each river by its riparian-zone width, in projected (UTM 37N) meters, returned back in WGS84."""
    rivers_gdf = rivers_gdf if rivers_gdf is not None else rivers_geodataframe()
    utm = rivers_gdf.to_crs(epsg=32637)
    buffered = utm.copy()
    buffered["geometry"] = [
        geom.buffer(_buffer_width_m(name)) for geom, name in zip(utm.geometry, utm["River"])
    ]
    buffered["buffer_m"] = [_buffer_width_m(name) for name in utm["River"]]
    return buffered.to_crs(epsg=4326)


def nearest_basin(lat: float, lon: float, rivers_gdf: gpd.GeoDataFrame | None = None) -> dict:
    """Assign a point to its nearest major river/basin (straight-line distance, indicative only)."""
    rivers_gdf = rivers_gdf if rivers_gdf is not None else rivers_geodataframe()
    from shapely.geometry import Point
    pt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=32637).iloc[0]
    utm_rivers = rivers_gdf.to_crs(epsg=32637)
    distances = utm_rivers.geometry.distance(pt)
    idx = distances.idxmin()
    return {
        "river": rivers_gdf.loc[idx, "River"],
        "basin": rivers_gdf.loc[idx, "Basin"],
        "distance_km": round(float(distances.loc[idx]) / 1000, 1),
    }


def assign_zones_to_basins(zones_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add River/Basin/DistanceToRiver_km/InRiparianBuffer/CarbonPriority columns
    to a zones DataFrame with lat/lon columns (works for sample or
    shapefile-loaded zones alike).
    """
    rivers_gdf = rivers_geodataframe()
    buffers_gdf = riparian_buffers(rivers_gdf)

    rivers = []
    basins = []
    distances = []
    in_buffer = []
    for row in zones_df.itertuples():
        info = nearest_basin(row.lat, row.lon, rivers_gdf)
        rivers.append(info["river"])
        basins.append(info["basin"])
        distances.append(info["distance_km"])
        in_buffer.append(info["distance_km"] <= (_buffer_width_m(info["river"]) / 1000.0) * 3)
        # "within buffer" uses a generous x3 tolerance on the indicative buffer width since these
        # are coarse polylines, not surveyed centerlines -- flags *candidate* riparian zones for
        # ground-truthing, not a legal riparian-setback determination.

    out = zones_df.copy()
    out["NearestRiver"] = rivers
    out["Basin"] = basins
    out["DistanceToRiver_km"] = distances
    out["RiparianZoneCandidate"] = in_buffer
    # Carbon-sequestration priority: riparian candidates score highest (revegetating/protecting
    # riparian corridors is one of the most cost-effective sequestration + biodiversity levers),
    # scaled down with distance from the nearest river.
    out["CarbonPriorityScore"] = [
        round(max(0.0, 100 - d * 8) * (1.3 if buf else 1.0), 1)
        for d, buf in zip(out["DistanceToRiver_km"], out["RiparianZoneCandidate"])
    ]
    out["CarbonPriorityScore"] = out["CarbonPriorityScore"].clip(upper=100)
    return out
