"""
Synthetic sample-data generator.

No real shapefiles/GeoTIFFs are shipped with this app (none were provided),
so this module builds realistic synthetic zone geometries, land-use mixes,
population, and rainfall for a set of Kenyan wards -- weighted toward the
North Rift, with a couple of Nairobi-metro wards kept for scenario
comparison variety. Everything here is deterministic (seeded) so cached
results stay stable across reruns.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from shapely.geometry import Polygon
from . import landcover_proxy, soil_hydrology, pollutant_loading

LAND_USES = ["Residential", "Commercial", "Industrial", "Agricultural"]

# (ward name, center lat, center lon, mean annual rainfall mm, typical CBD flavor)
WARDS = [
    ("Kapsoya (Eldoret)", 0.5050, 35.2699, 1150),
    ("Kimumu (Eldoret)", 0.5427, 35.2698, 1150),
    ("Kapsabet Town", 0.2035, 35.1050, 1400),
    ("Iten", 0.6710, 35.5090, 1100),
    ("Kahawa Wendani", -1.1900, 36.9350, 950),
    ("Ruiru", -1.1460, 36.9630, 1000),
]

ZONES_PER_WARD = 6


def _ward_zone_grid(center_lat: float, center_lon: float, n: int, seed: int):
    """Lay out n roughly-square zone polygons on a small grid around a center point."""
    rng = np.random.default_rng(seed)
    cols = int(np.ceil(np.sqrt(n)))
    step = 0.006  # ~650m per grid cell
    polygons = []
    centroids = []
    idx = 0
    for r in range(cols):
        for c in range(cols):
            if idx >= n:
                break
            jitter_lat = rng.uniform(-0.0008, 0.0008)
            jitter_lon = rng.uniform(-0.0008, 0.0008)
            lat0 = center_lat + (r - cols / 2) * step + jitter_lat
            lon0 = center_lon + (c - cols / 2) * step + jitter_lon
            poly = Polygon([
                (lon0, lat0), (lon0 + step * 0.9, lat0),
                (lon0 + step * 0.9, lat0 + step * 0.9), (lon0, lat0 + step * 0.9),
            ])
            polygons.append(poly)
            centroids.append((lat0 + step * 0.45, lon0 + step * 0.45))
            idx += 1
    return polygons, centroids


def generate_zones(seed: int = 42) -> pd.DataFrame:
    """Build the master zone table: geometry + attributes for every ward."""
    rng = np.random.default_rng(seed)
    rows = []
    for w_i, (ward, lat, lon, rainfall_base) in enumerate(WARDS):
        polys, centroids = _ward_zone_grid(lat, lon, ZONES_PER_WARD, seed=seed + w_i)
        land_use_cycle = (LAND_USES * ((ZONES_PER_WARD // len(LAND_USES)) + 1))[:ZONES_PER_WARD]
        rng.shuffle(land_use_cycle)
        for z_i in range(ZONES_PER_WARD):
            land_use = land_use_cycle[z_i]
            zone_seed = seed + w_i * 1000 + z_i
            landcover = landcover_proxy.sample_landcover(land_use, seed=zone_seed)
            impervious = landcover_proxy.estimate_imperviousness(landcover, seed=zone_seed)
            hsg = soil_hydrology.assign_hsg_proxy(land_use, seed=zone_seed)
            point_source = pollutant_loading.has_point_source(land_use, seed=zone_seed)
            population = int(rng.uniform(800, 6000)) if land_use != "Agricultural" else int(rng.uniform(100, 900))
            rainfall_mm = float(rainfall_base / 12 * rng.uniform(0.8, 1.3))  # a "monthly design storm" depth
            rows.append({
                "Ward": ward,
                "Zone": f"{ward.split(' ')[0]}-Z{z_i + 1}",
                "LandUse": land_use,
                "LandCover": landcover,
                "ImperviousSurface": round(impervious, 1),
                "HSG": hsg,
                "PointSource": point_source,
                "Population": population,
                "MeanRainfall_mm": round(rainfall_mm, 1),
                "geometry": polys[z_i],
                "lat": centroids[z_i][0],
                "lon": centroids[z_i][1],
            })
    return pd.DataFrame(rows)


def ward_center(ward: str) -> tuple[float, float]:
    for name, lat, lon, _ in WARDS:
        if name == ward:
            return lat, lon
    return -1.175, 36.955
