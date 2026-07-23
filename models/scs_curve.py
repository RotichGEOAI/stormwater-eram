"""
SCS (NRCS) Curve Number method for direct runoff estimation, using the
standard TR-55 land-use x Hydrologic Soil Group (HSG) curve-number table
(see utils/soil_hydrology.py) instead of a flat per-land-use base CN.
"""

from __future__ import annotations
import numpy as np
from utils import soil_hydrology


def calculate_runoff(land_use: str, impervious_surface: float, rainfall_mm: float,
                      hsg: str = "C") -> dict:
    """Estimate runoff depth (mm) using the standard SCS-CN equation."""
    cn_base = soil_hydrology.curve_number(land_use, hsg)
    cn = cn_base + (impervious_surface / 100.0) * (98 - cn_base)
    cn = float(np.clip(cn, 30, 98))

    s = (25400.0 / cn) - 254.0
    ia = 0.2 * s

    if rainfall_mm > ia:
        q = ((rainfall_mm - ia) ** 2) / (rainfall_mm - ia + s)
    else:
        q = 0.0

    return {
        "method": "SCS Curve",
        "curve_number": round(cn, 1),
        "hsg": hsg,
        "runoff_mm": round(float(q), 2),
    }
