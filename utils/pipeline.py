"""
Runs the LTHIA-LID/SCS-CN flood models, lifecycle cost-benefit analysis,
point/non-point pollutant loading, and disease-risk screening over every
(zone x scenario) combination in a zones DataFrame. Shared by the cached
built-in sample pipeline and the on-demand pipeline for shapefile-loaded
wards, so both produce the exact same output schema.

Zones are expected to carry HSG (Hydrologic Soil Group) and PointSource
columns (see data_generator.py / shapefile_loader.py) — if they're
missing (e.g. an older/hand-built zones table), sensible defaults are
substituted so the pipeline doesn't break.
"""

from __future__ import annotations
import pandas as pd

from models import flood_prediction
from . import cost_benefit, pollutant_loading, disease_risk, climate_scenarios, watershed

SCENARIO_ORDER = ["Grey", "Hybrid", "Green"]

# Share of a zone's population assumed exposed/affected at each flood-risk level —
# a planning-level proxy (informed by the general pattern that flood exposure scales
# with risk classification), not a hydraulic inundation-extent model.
_RISK_EXPOSURE_SHARE = {"Low": 0.05, "Moderate": 0.25, "High": 0.55}


def run_models(zones_df: pd.DataFrame, scenarios=None, ssp_key: str | None = None,
               climate_flavor: str = "Warm") -> pd.DataFrame:
    """
    ssp_key / climate_flavor: if given, adjusts each zone's baseline rainfall
    through utils.climate_scenarios before running the flood models — lets
    the same zone table be re-run under different SSP-RCP x wet/dry/warm/hot
    futures without touching the underlying sample/uploaded data.
    """
    scenarios = scenarios or SCENARIO_ORDER
    zones_df = watershed.assign_zones_to_basins(zones_df)
    records = []
    for row in zones_df.itertuples():
        hsg = getattr(row, "HSG", "C")
        point_source = bool(getattr(row, "PointSource", False))

        rainfall_mm = row.MeanRainfall_mm
        if ssp_key:
            adjusted = climate_scenarios.adjust_rainfall_temp(rainfall_mm, ssp_key, climate_flavor)
            rainfall_mm = adjusted["rainfall_mm"]

        for scenario in scenarios:
            flood = flood_prediction.predict(row.LandUse, row.ImperviousSurface,
                                              rainfall_mm, scenario, hsg)
            econ = cost_benefit.analyze(scenario, row.Population, rainfall_mm,
                                         row.ImperviousSurface)
            pollutants = pollutant_loading.estimate_loads(
                row.LandUse, flood["average_runoff_mm"], row.geometry, scenario, point_source)
            diseases = disease_risk.assess_disease_risk(flood["flood_risk"], climate_flavor)
            pop_at_risk = int(round(row.Population * _RISK_EXPOSURE_SHARE.get(flood["flood_risk"], 0.05)))

            records.append({
                "Ward": row.Ward, "Zone": row.Zone, "LandUse": row.LandUse,
                "LandCover": getattr(row, "LandCover", "n/a"),
                "ImperviousSurface": row.ImperviousSurface, "HSG": hsg, "PointSource": point_source,
                "Population": row.Population, "PopulationAtRisk": pop_at_risk,
                "MeanRainfall_mm": round(rainfall_mm, 1),
                "lat": row.lat, "lon": row.lon, "geometry": row.geometry, "Scenario": scenario,
                "LTHIA_Runoff_mm": flood["lthia_runoff_mm"], "SCS_Runoff_mm": flood["scs_runoff_mm"],
                "Average_Runoff_mm": flood["average_runoff_mm"],
                "Peak_Attenuation_pct": flood["peak_attenuation_pct"],
                "FloodRisk": flood["flood_risk"],
                "TSS_kg": pollutants["TSS"], "TN_kg": pollutants["TN"], "TP_kg": pollutants["TP"],
                "FecalColiform_index": pollutants["FecalColiform"],
                "DiseaseRisk": diseases,
                "NearestRiver": row.NearestRiver, "Basin": row.Basin,
                "DistanceToRiver_km": row.DistanceToRiver_km,
                "RiparianZoneCandidate": row.RiparianZoneCandidate,
                "CarbonPriorityScore": row.CarbonPriorityScore,
                **econ,
            })
    df = pd.DataFrame(records)
    df["Scenario"] = pd.Categorical(df["Scenario"], categories=SCENARIO_ORDER, ordered=True)
    return df
