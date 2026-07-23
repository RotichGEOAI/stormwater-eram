"""
Builds a per-zone infrastructure scenario record (Green / Hybrid / Grey)
combining the zone's physical attributes with the chosen strategy.
"""

from __future__ import annotations

SCENARIO_DESCRIPTIONS = {
    "Green": "Bioswales, constructed wetlands, permeable pavements",
    "Hybrid": "Detention ponds combined with engineered drainage",
    "Grey": "Conventional stormwater pipes and culverts",
}


def build_scenario(land_use: str, impervious_surface: float, population: int,
                    rainfall_mm: float, scenario_type: str) -> dict:
    return {
        "land_use": land_use,
        "impervious_surface_pct": impervious_surface,
        "population": population,
        "rainfall_mm": rainfall_mm,
        "scenario_type": scenario_type,
        "description": SCENARIO_DESCRIPTIONS.get(scenario_type, ""),
    }
