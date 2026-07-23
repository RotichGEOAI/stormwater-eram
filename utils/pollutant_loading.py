"""
Point-source and non-point-source (NPS) pollutant loading, in the spirit
of LTHIA's own pollutant-loading module (LTHIA = Long-Term Hydrologic
Impact Assessment, which pairs runoff depth with event-mean-concentration
water-quality estimates, not just flood depth).

Non-point source: Load = Runoff volume x Event Mean Concentration (EMC),
using standard National Stormwater Quality Database-style EMC ranges by
land use, for TSS, Total Nitrogen, Total Phosphorus, and fecal coliform.

Point source: a fixed anthropogenic load added for zones flagged as
hosting a discharge point (industrial outfall, informal settlement pit
latrine drainage, etc.) — a simple additive term, not a hydraulic model.
"""

from __future__ import annotations
import geopandas as gpd
import numpy as np
from shapely.geometry.base import BaseGeometry

# Event Mean Concentrations (mg/L), fecal coliform in cfu/100mL
EMC_TABLE = {
    "Residential": {"TSS": 60, "TN": 2.0, "TP": 0.3, "FecalColiform": 5000},
    "Commercial": {"TSS": 40, "TN": 1.5, "TP": 0.2, "FecalColiform": 2000},
    "Industrial": {"TSS": 80, "TN": 1.0, "TP": 0.15, "FecalColiform": 1000},
    "Agricultural": {"TSS": 100, "TN": 5.0, "TP": 0.8, "FecalColiform": 20000},
}

# Fixed annual point-source addition (kg/yr) when a zone hosts a discharge point.
POINT_SOURCE_LOAD_KG_YR = {"TSS": 800, "TN": 120, "TP": 25, "FecalColiform_index": 500}

# LID/scenario treatment efficiency (fractional pollutant removal), applied
# on top of the runoff-volume reduction the flood model already captures.
_TREATMENT_EFFICIENCY = {"Green": 0.65, "Hybrid": 0.35, "Grey": 0.05}


def zone_area_m2(geometry: BaseGeometry) -> float:
    """Reproject a single WGS84 geometry to UTM 37N (Kenya) and return its area in m2."""
    gs = gpd.GeoSeries([geometry], crs="EPSG:4326")
    return float(gs.to_crs(epsg=32637).area.iloc[0])


def has_point_source(land_use: str, seed: int) -> bool:
    """Deterministic (seeded) flag: commercial/industrial zones more likely to host a discharge point."""
    rng = np.random.default_rng(seed)
    prob = {"Industrial": 0.45, "Commercial": 0.25, "Residential": 0.08, "Agricultural": 0.05}.get(land_use, 0.1)
    return bool(rng.uniform() < prob)


def estimate_loads(land_use: str, runoff_mm: float, geometry: BaseGeometry,
                    scenario_type: str = "Grey", point_source: bool = False) -> dict:
    """
    Estimate annual pollutant loads (kg/yr, fecal coliform as a relative
    index) for one zone under one infrastructure scenario.
    """
    area_m2 = zone_area_m2(geometry)
    runoff_volume_m3 = (runoff_mm / 1000.0) * area_m2
    emc = EMC_TABLE.get(land_use, EMC_TABLE["Residential"])
    efficiency = _TREATMENT_EFFICIENCY.get(scenario_type, 0.05)

    loads = {}
    for pollutant, conc_mg_l in emc.items():
        if pollutant == "FecalColiform":
            # Relative loading index rather than a true mass load (concentration-based indicator)
            raw = runoff_volume_m3 * conc_mg_l / 1000.0
        else:
            raw = runoff_volume_m3 * conc_mg_l / 1000.0  # m3 * mg/L -> kg (1 m3 = 1000 L, mg/1e6 = kg)
        treated = raw * (1 - efficiency)
        loads[pollutant] = round(treated, 2)

    if point_source:
        loads["TSS"] = round(loads["TSS"] + POINT_SOURCE_LOAD_KG_YR["TSS"] * (1 - efficiency * 0.3), 2)
        loads["TN"] = round(loads["TN"] + POINT_SOURCE_LOAD_KG_YR["TN"] * (1 - efficiency * 0.3), 2)
        loads["TP"] = round(loads["TP"] + POINT_SOURCE_LOAD_KG_YR["TP"] * (1 - efficiency * 0.3), 2)
        loads["FecalColiform"] = round(loads["FecalColiform"] + POINT_SOURCE_LOAD_KG_YR["FecalColiform_index"], 2)

    loads["point_source_present"] = point_source
    return loads
