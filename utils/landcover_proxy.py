"""
Imperviousness proxy derived from land-cover class, standing in for a true
per-pixel impervious-surface raster.

In production this would sample a Sentinel-2-derived land-cover product —
e.g. ESA WorldCover (10m, free, global, available via the Copernicus Data
Space or as a Google Earth Engine asset) or Esri's Sentinel-2 Land Cover
layer on ArcGIS Living Atlas — at each zone's geometry and take the
majority class. That step needs network access to a tile/asset service
this sandbox doesn't have credentials for, so `estimate_imperviousness()`
below uses the standard WorldCover/Living Atlas class taxonomy with
published imperviousness ranges as a stand-in. Swap `sample_landcover()`
for a real raster/GEE query and the rest of the pipeline is unaffected.
"""

from __future__ import annotations
import numpy as np

# ESA WorldCover / Esri Living Atlas class taxonomy, with an indicative
# imperviousness midpoint per class (percent).
LANDCOVER_CLASSES = [
    "Built-up (dense)", "Built-up (sparse)", "Cropland", "Grassland",
    "Bare / sparse vegetation", "Shrubland", "Wetland", "Water",
]

_IMPERVIOUS_MIDPOINT = {
    "Built-up (dense)": 82, "Built-up (sparse)": 48, "Cropland": 14,
    "Grassland": 7, "Bare / sparse vegetation": 35, "Shrubland": 10,
    "Wetland": 3, "Water": 0,
}

# Rough land-use -> plausible land-cover mix, used only to keep the proxy
# internally consistent with the zoning-style LandUse field already in the
# sample/uploaded zone tables.
_LAND_USE_TO_LANDCOVER_WEIGHTS = {
    "Residential": {"Built-up (dense)": 0.35, "Built-up (sparse)": 0.45, "Grassland": 0.20},
    "Commercial": {"Built-up (dense)": 0.80, "Built-up (sparse)": 0.20},
    "Industrial": {"Built-up (dense)": 0.65, "Bare / sparse vegetation": 0.25, "Built-up (sparse)": 0.10},
    "Agricultural": {"Cropland": 0.65, "Grassland": 0.25, "Shrubland": 0.10},
}


def sample_landcover(land_use: str, seed: int) -> str:
    """
    Stand-in for a real Sentinel-2/Living Atlas majority-class sample at a
    zone's geometry. Replace with an actual raster/GEE query keyed on the
    zone's centroid or bounding geometry for production use.
    """
    rng = np.random.default_rng(seed)
    weights = _LAND_USE_TO_LANDCOVER_WEIGHTS.get(land_use, {"Built-up (sparse)": 1.0})
    classes, probs = zip(*weights.items())
    return str(rng.choice(classes, p=probs))


def estimate_imperviousness(landcover_class: str, seed: int = 0, noise_pct: float = 6.0) -> float:
    """Indicative imperviousness (%) for a land-cover class, with small realistic noise."""
    rng = np.random.default_rng(seed)
    midpoint = _IMPERVIOUS_MIDPOINT.get(landcover_class, 50)
    value = midpoint + rng.uniform(-noise_pct, noise_pct)
    return float(np.clip(value, 0, 98))
