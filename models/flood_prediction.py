"""
Combines LTHIA-LID and SCS-CN runoff estimates (both HSG-aware) into a
single flood-risk assessment, with a peak-flow attenuation estimate for
performance tracking.
"""

from __future__ import annotations
from . import lthia_lid, scs_curve

# Runoff thresholds (mm) separating Low / Moderate / High flood risk.
# Calibrated loosely against tropical convective storm depths typical of
# East African urban catchments.
_RISK_THRESHOLDS = (15.0, 35.0)


def classify_risk(runoff_mm: float) -> str:
    low, high = _RISK_THRESHOLDS
    if runoff_mm < low:
        return "Low"
    if runoff_mm < high:
        return "Moderate"
    return "High"


def combine(runoff_lthia: dict, runoff_scs: dict) -> dict:
    """Average the two independent runoff estimates and classify risk."""
    avg_runoff = round((runoff_lthia["runoff_mm"] + runoff_scs["runoff_mm"]) / 2, 2)
    risk = classify_risk(avg_runoff)
    return {
        "lthia_runoff_mm": runoff_lthia["runoff_mm"],
        "scs_runoff_mm": runoff_scs["runoff_mm"],
        "average_runoff_mm": avg_runoff,
        "flood_risk": risk,
    }


def predict(land_use: str, impervious_surface: float, rainfall_mm: float,
            scenario_type: str = "Grey", hsg: str = "C") -> dict:
    """One-call flood prediction for a zone under a given scenario, given its Hydrologic Soil Group."""
    lthia = lthia_lid.run_model(land_use, impervious_surface, rainfall_mm, scenario_type, hsg)
    scs = scs_curve.calculate_runoff(land_use, impervious_surface, rainfall_mm, hsg)
    result = combine(lthia, scs)

    baseline_runoff = combine(
        lthia_lid.run_model(land_use, impervious_surface, rainfall_mm, "Grey", hsg),
        scs,
    )["average_runoff_mm"]
    if baseline_runoff > 0:
        peak_attenuation_pct = max(0.0, round(
            (1 - result["average_runoff_mm"] / baseline_runoff) * 100, 1))
    else:
        peak_attenuation_pct = 0.0

    result["peak_attenuation_pct"] = peak_attenuation_pct
    result["hsg"] = hsg
    return result
