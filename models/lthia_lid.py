"""
Simplified LTHIA-LID (Long-Term Hydrologic Impact Assessment – Low Impact
Development) runoff estimator, based on the SCS Curve Number method with
Hydrologic-Soil-Group-aware base curve numbers (utils/soil_hydrology.py)
and a green-infrastructure adjustment.
"""

from __future__ import annotations
import numpy as np
from utils import soil_hydrology

# Runoff-reduction multiplier applied by LID/green measures, by scenario type
_LID_REDUCTION = {
    "Green": 0.55,   # bioswales / wetlands / permeable pavement cut effective CN increase
    "Hybrid": 0.75,
    "Grey": 1.0,     # no LID credit
}


def effective_curve_number(land_use: str, impervious_pct: float, scenario_type: str = "Grey",
                            hsg: str = "C") -> float:
    """Blend the HSG-based land-use CN with imperviousness, then apply the LID credit."""
    cn_base = soil_hydrology.curve_number(land_use, hsg)
    cn_impervious = cn_base + (impervious_pct / 100.0) * (98 - cn_base)
    lid_factor = _LID_REDUCTION.get(scenario_type, 1.0)
    # LID only discounts the *increase* over the base CN, not the base itself
    cn_effective = cn_base + (cn_impervious - cn_base) * lid_factor
    return float(np.clip(cn_effective, 30, 98))


def run_model(land_use: str, impervious_surface: float, rainfall_mm: float,
              scenario_type: str = "Grey", hsg: str = "C") -> dict:
    """
    Estimate runoff depth using an LTHIA-LID-style SCS-CN calculation.

    Returns a dict with the effective curve number and runoff depth (mm).
    """
    cn = effective_curve_number(land_use, impervious_surface, scenario_type, hsg)
    s = (25400.0 / cn) - 254.0          # potential maximum retention (mm)
    ia = 0.2 * s                         # initial abstraction (mm)

    if rainfall_mm > ia:
        q = ((rainfall_mm - ia) ** 2) / (rainfall_mm - ia + s)
    else:
        q = 0.0

    return {
        "method": "LTHIA-LID",
        "curve_number": round(cn, 1),
        "hsg": hsg,
        "runoff_mm": round(float(q), 2),
    }
