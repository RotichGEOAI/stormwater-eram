"""
Indicative disease-risk screening tied to flood-risk level and climate
flavor, based on well-established flood-public-health linkages (WHO flood
guidance; post-flood outbreak literature for East Africa): standing water
and breached sanitation drive waterborne/diarrheal disease and cholera;
stagnant water expands mosquito/snail vector habitat (malaria, dengue,
schistosomiasis); contact with contaminated floodwater raises
leptospirosis risk; heavy rains after dry spells are a classic Rift Valley
Fever trigger in Kenyan livestock-keeping areas.

This is a population-level planning/awareness screen, not a diagnostic or
epidemiological forecasting tool — pair with local health-authority
surveillance data before acting on it.
"""

from __future__ import annotations

_SEVERITY_ORDER = ["None", "Low", "Moderate", "High", "Severe"]

# Baseline disease-risk severity by flood-risk level.
_BASE_RISK = {
    "Low": {"Diarrheal disease": "Low", "Malaria": "Low"},
    "Moderate": {"Diarrheal disease": "Moderate", "Typhoid": "Low", "Malaria": "Moderate",
                 "Leptospirosis": "Low"},
    "High": {"Cholera": "Moderate", "Diarrheal disease": "High", "Typhoid": "Moderate",
             "Malaria": "High", "Leptospirosis": "Moderate", "Schistosomiasis": "Low",
             "Rift Valley Fever": "Low"},
}

# How each climate flavor shifts severity, in steps along _SEVERITY_ORDER,
# per disease category (waterborne, vector-borne, contact, epizootic).
_FLAVOR_STEP = {
    "Wet": {"waterborne": +1, "vector": +1, "contact": +1, "epizootic": +1},
    "Dry": {"waterborne": -1, "vector": -1, "contact": 0, "epizootic": 0},
    "Warm": {"waterborne": 0, "vector": 0, "contact": 0, "epizootic": 0},
    "Hot": {"waterborne": 0, "vector": +1, "contact": 0, "epizootic": 0},
}

_DISEASE_CATEGORY = {
    "Cholera": "waterborne", "Diarrheal disease": "waterborne", "Typhoid": "waterborne",
    "Malaria": "vector", "Schistosomiasis": "vector",
    "Leptospirosis": "contact",
    "Rift Valley Fever": "epizootic",
}


def _step_severity(level: str, steps: int) -> str:
    idx = _SEVERITY_ORDER.index(level) if level in _SEVERITY_ORDER else 0
    idx = max(0, min(len(_SEVERITY_ORDER) - 1, idx + steps))
    return _SEVERITY_ORDER[idx]


def assess_disease_risk(flood_risk: str, climate_flavor: str = "Warm") -> dict:
    """Return {disease: severity} for a given flood-risk level and climate flavor."""
    base = _BASE_RISK.get(flood_risk, _BASE_RISK["Low"])
    shifts = _FLAVOR_STEP.get(climate_flavor, _FLAVOR_STEP["Warm"])

    result = {}
    for disease, severity in base.items():
        category = _DISEASE_CATEGORY.get(disease, "waterborne")
        result[disease] = _step_severity(severity, shifts.get(category, 0))
    # Drop anything that stepped down to "None" so the list stays actionable.
    return {d: s for d, s in result.items() if s != "None"}
