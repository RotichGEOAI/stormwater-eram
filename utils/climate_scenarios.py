"""
Shared Socioeconomic Pathway (SSP) x Representative Concentration Pathway
(RCP) climate scenarios, paired with a wet/dry/warm/hot climate-flavor
modifier, used to adjust the rainfall/temperature inputs fed into the
flood models and to shape the infrastructure-scenario narrative.

The per-SSP deltas below are indicative, mid-century (~2050), East-Africa
regional order-of-magnitude figures consistent with the general direction
of CMIP6 multi-model ensembles summarized in IPCC AR6 WG1 regional fact
sheets -- they are NOT a downscaled climate projection for any specific
site. Swap in real downscaled CMIP6/CORDEX-Africa deltas for a specific
ward if you have them (this module is the single place that would change).
"""

from __future__ import annotations

SSP_SCENARIOS = {
    "SSP1-1.9": {"label": "Very Low Emissions", "temp_delta_C": 0.6, "rainfall_delta_pct": 2},
    "SSP1-2.6": {"label": "Low Emissions", "temp_delta_C": 1.0, "rainfall_delta_pct": 4},
    "SSP2-4.5": {"label": "Intermediate Emissions", "temp_delta_C": 1.8, "rainfall_delta_pct": 7},
    "SSP3-7.0": {"label": "High Emissions", "temp_delta_C": 2.6, "rainfall_delta_pct": 11},
    "SSP5-8.5": {"label": "Very High Emissions", "temp_delta_C": 3.4, "rainfall_delta_pct": 15},
}

SSP_ORDER = ["SSP1-1.9", "SSP1-2.6", "SSP2-4.5", "SSP3-7.0", "SSP5-8.5"]

# Within an SSP, which "climate possibility" the planner wants to stress-test.
CLIMATE_FLAVORS = {
    "Wet": {"rainfall_multiplier": 1.25, "temp_offset_C": 0.0,
            "description": "Above-normal rainfall — wetter short/long rains, higher flood exposure."},
    "Dry": {"rainfall_multiplier": 0.70, "temp_offset_C": 0.5,
            "description": "Below-normal rainfall — drought-leaning, lower flood but higher water-stress exposure."},
    "Warm": {"rainfall_multiplier": 1.00, "temp_offset_C": 1.0,
             "description": "Near-normal rainfall with moderate warming."},
    "Hot": {"rainfall_multiplier": 0.85, "temp_offset_C": 2.0,
            "description": "Reduced rainfall with pronounced warming — heat-stress and vector-range risk."},
}

CLIMATE_FLAVOR_ORDER = ["Wet", "Dry", "Warm", "Hot"]

_BASELINE_TEMP_C = 22.0  # rough North Rift / mid-elevation Kenya baseline mean temperature


def adjust_rainfall_temp(base_rainfall_mm: float, ssp_key: str, flavor_key: str,
                          base_temp_c: float = _BASELINE_TEMP_C) -> dict:
    """Apply an SSP-RCP delta and a climate-flavor multiplier to a baseline rainfall/temperature pair."""
    ssp = SSP_SCENARIOS.get(ssp_key, SSP_SCENARIOS["SSP2-4.5"])
    flavor = CLIMATE_FLAVORS.get(flavor_key, CLIMATE_FLAVORS["Warm"])

    rainfall = base_rainfall_mm * (1 + ssp["rainfall_delta_pct"] / 100.0) * flavor["rainfall_multiplier"]
    temp = base_temp_c + ssp["temp_delta_C"] + flavor["temp_offset_C"]

    return {
        "rainfall_mm": round(float(rainfall), 1),
        "temp_c": round(float(temp), 1),
        "ssp_label": ssp["label"],
        "flavor_description": flavor["description"],
    }


def recommend_infrastructure_mix(ssp_key: str, flavor_key: str) -> str:
    """Short planning narrative nudging toward Green/Hybrid under higher-stress futures."""
    ssp = SSP_SCENARIOS.get(ssp_key, SSP_SCENARIOS["SSP2-4.5"])
    severity_rank = SSP_ORDER.index(ssp_key) if ssp_key in SSP_ORDER else 2

    if severity_rank <= 1:
        lean = ("Grey infrastructure remains viable at reasonable lifecycle cost; "
                "Hybrid is still worth piloting where budget allows for future-proofing.")
    elif severity_rank == 2:
        lean = "Hybrid infrastructure offers the best balance of cost and resilience at this pathway."
    else:
        lean = ("Green (or Green-led Hybrid) infrastructure is strongly favored — peak attenuation "
                "and co-benefits scale with the storm intensity this pathway implies.")

    return (f"Under {ssp_key} ({ssp['label']}) combined with {flavor_key.lower()} conditions "
            f"({CLIMATE_FLAVORS.get(flavor_key, {}).get('description', '')}): {lean}")
