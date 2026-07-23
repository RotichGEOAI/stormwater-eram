"""
Hydrologic Soil Group (HSG A-D) handling for the SCS-CN and LTHIA-LID models.

SSURGO (the Soil Survey Geographic Database) is an NRCS/USDA product and
only covers the United States -- it does not exist for Kenya. The
globally-applicable equivalent is a texture-derived HSG estimate from
ISRIC SoilGrids (250m global soil property maps, covers Kenya) or the
Africa Soil Information Service (AfSIS). This module provides:

  1. The standard NRCS TR-55 curve-number lookup table by land use x HSG
     (the actual number-crunching machinery both flood models need), and
  2. A texture-class -> HSG mapping plus a deterministic proxy assigner,
     so the app runs end-to-end today without a live SoilGrids call.

To wire in real SoilGrids data: fetch the dominant WRB soil texture class
for a zone's centroid from https://rest.isric.org (ISRIC's SoilGrids REST
API) and pass it through `hsg_from_texture()` instead of
`assign_hsg_proxy()`.
"""

from __future__ import annotations
import numpy as np

HSG_CLASSES = ["A", "B", "C", "D"]

HSG_DESCRIPTIONS = {
    "A": "Low runoff potential — deep, well-drained sands/loamy sands.",
    "B": "Moderately low runoff potential — moderately deep, well-drained loams.",
    "C": "Moderately high runoff potential — soils with a layer impeding downward drainage.",
    "D": "High runoff potential — clay soils or shallow soils over near-impervious material.",
}

# Standard NRCS TR-55 curve numbers, AMC-II, by land use x HSG.
CN_TABLE = {
    "Residential": {"A": 57, "B": 72, "C": 81, "D": 86},
    "Commercial": {"A": 89, "B": 92, "C": 94, "D": 95},
    "Industrial": {"A": 81, "B": 88, "C": 91, "D": 93},
    "Agricultural": {"A": 67, "B": 78, "C": 85, "D": 89},
}

# Texture class -> HSG, per NRCS guidance (dominant surface texture).
_TEXTURE_TO_HSG = {
    "sand": "A", "loamy sand": "A",
    "sandy loam": "B", "loam": "B", "silt loam": "B",
    "sandy clay loam": "C", "clay loam": "C", "silty clay loam": "C",
    "sandy clay": "D", "silty clay": "D", "clay": "D",
}


def hsg_from_texture(texture_class: str) -> str:
    """Map a SoilGrids/AfSIS-style texture class name to an HSG letter."""
    return _TEXTURE_TO_HSG.get(texture_class.strip().lower(), "C")


def assign_hsg_proxy(land_use: str, seed: int) -> str:
    """
    Deterministic placeholder HSG assignment (seeded per zone) used until a
    real SoilGrids/AfSIS lookup is wired in. Weighted so agricultural/rural
    zones skew toward better-drained soils (A/B) and dense built-up zones
    skew toward compacted/poorly-drained soils (C/D), matching the broad
    real-world correlation between land development and soil compaction.
    """
    rng = np.random.default_rng(seed)
    weights = {
        "Agricultural": [0.30, 0.40, 0.20, 0.10],
        "Residential": [0.15, 0.30, 0.35, 0.20],
        "Commercial": [0.10, 0.20, 0.35, 0.35],
        "Industrial": [0.10, 0.20, 0.35, 0.35],
    }.get(land_use, [0.2, 0.3, 0.3, 0.2])
    return str(rng.choice(HSG_CLASSES, p=weights))


def curve_number(land_use: str, hsg: str) -> int:
    return CN_TABLE.get(land_use, CN_TABLE["Residential"]).get(hsg, 81)
