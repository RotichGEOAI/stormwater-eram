"""
Lifecycle cost-benefit analysis: CAPEX/OPEX, NPV/BCR/payback, and
environmental co-benefit scoring (carbon sequestration, urban cooling,
biodiversity) per infrastructure scenario.

Unit costs are indicative planning-level figures (USD), not procurement
quotes -- intended for relative scenario comparison, not budgeting.
"""

from __future__ import annotations
import numpy as np

# USD per served-resident, indicative planning-level unit costs
_CAPEX_PER_CAPITA = {"Green": 38.0, "Hybrid": 52.0, "Grey": 65.0}
_OPEX_PCT_OF_CAPEX = {"Green": 0.03, "Hybrid": 0.05, "Grey": 0.07}  # annual O&M as % of CAPEX

# Co-benefit indices (0-100 scale) by scenario, before zone-level scaling
_CO_BENEFITS_BASE = {
    "Green": {"Carbon_Sequestration": 70, "Urban_Cooling": 65, "Biodiversity_Index": 75},
    "Hybrid": {"Carbon_Sequestration": 35, "Urban_Cooling": 30, "Biodiversity_Index": 30},
    "Grey": {"Carbon_Sequestration": 5, "Urban_Cooling": 5, "Biodiversity_Index": 5},
}

_DISCOUNT_RATE = 0.08
_LIFECYCLE_YEARS = 20
# Annual monetized benefit per capita from avoided flood damage + ecosystem
# services, scaled by scenario effectiveness (used for NPV/BCR/payback only)
_BENEFIT_PER_CAPITA = {"Green": 9.5, "Hybrid": 7.0, "Grey": 4.0}


def analyze(scenario_type: str, population: int, rainfall_mm: float,
            impervious_surface: float = 50.0) -> dict:
    """Return CAPEX/OPEX, financial metrics, and co-benefit scores for a scenario."""
    capex = _CAPEX_PER_CAPITA[scenario_type] * population
    opex_annual = capex * _OPEX_PCT_OF_CAPEX[scenario_type]

    benefit_annual = _BENEFIT_PER_CAPITA[scenario_type] * population * (1 + rainfall_mm / 200)

    years = np.arange(1, _LIFECYCLE_YEARS + 1)
    discount_factors = 1 / (1 + _DISCOUNT_RATE) ** years
    pv_benefits = np.sum(benefit_annual * discount_factors)
    pv_costs = capex + np.sum(opex_annual * discount_factors)

    npv = pv_benefits - pv_costs
    bcr = pv_benefits / pv_costs if pv_costs > 0 else 0.0
    payback_years = capex / (benefit_annual - opex_annual) if (benefit_annual - opex_annual) > 0 else float("inf")

    co = _CO_BENEFITS_BASE[scenario_type]
    impervious_factor = 1 + (impervious_surface - 50) / 200  # denser sites amplify green co-benefits slightly

    return {
        "CAPEX_USD": round(capex, 2),
        "OPEX_USD": round(opex_annual, 2),
        "NPV_USD": round(float(npv), 2),
        "BCR": round(float(bcr), 2),
        "Payback_Years": round(float(payback_years), 1) if payback_years != float("inf") else None,
        "Carbon_Sequestration": round(co["Carbon_Sequestration"] * impervious_factor, 1),
        "Urban_Cooling": round(co["Urban_Cooling"] * impervious_factor, 1),
        "Biodiversity_Index": round(co["Biodiversity_Index"] * impervious_factor, 1),
    }
