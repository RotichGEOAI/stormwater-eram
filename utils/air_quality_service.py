"""
Air quality lookups for a ward, via AirQo (https://airqo.net) — a
Pan-African low-cost air-quality sensor network with real public API
coverage across Kenya — with AfriqAir (a pan-African coordinating network
of air-quality monitoring initiatives, https://afriqair.org) as a
secondary/complementary attribution rather than a second live endpoint,
since AfriqAir itself is a coalition/data-sharing initiative rather than
a single queryable API.

AirQo's public "measurements" API needs an API token (free to register
for at https://docs.airqo.net). This sandbox has no token and its network
policy blocks arbitrary outbound hosts, so the live call can't be
exercised here — but it degrades safely: any missing token, network
failure, or non-200 response falls back to a seeded synthetic AQI series
so the rest of the app keeps working. Set the AIRQO_API_TOKEN environment
variable (or Streamlit secret) to enable the live path.
"""

from __future__ import annotations
import os
import numpy as np

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

_AIRQO_MEASUREMENTS_URL = "https://api.airqo.net/api/v2/devices/measurements/nearest"

AQI_BANDS = [
    (0, 50, "Good", "#2e7d32"),
    (50, 100, "Moderate", "#f9a825"),
    (100, 150, "Unhealthy (sensitive groups)", "#ef6c00"),
    (150, 200, "Unhealthy", "#c62828"),
    (200, 300, "Very Unhealthy", "#6a1b9a"),
    (300, 500, "Hazardous", "#4a0e0e"),
]


def classify_aqi(pm25: float) -> tuple[str, str]:
    """US EPA-style AQI band label + color for a PM2.5 concentration (µg/m3), treated as an AQI-like index."""
    for low, high, label, color in AQI_BANDS:
        if low <= pm25 < high:
            return label, color
    return "Hazardous", AQI_BANDS[-1][3]


def _synthetic_air_quality(lat: float, lon: float) -> dict:
    """Deterministic fallback reading, seeded on location so repeated calls are stable."""
    seed = int(abs(lat * 1000) + abs(lon * 1000)) + 7
    rng = np.random.default_rng(seed)
    pm25 = round(float(rng.uniform(8, 65)), 1)
    label, color = classify_aqi(pm25)
    return {
        "source": "simulated (offline fallback — AirQo/AfriqAir live not reachable)",
        "pm2_5": pm25,
        "aqi_label": label,
        "aqi_color": color,
    }


def get_air_quality(lat: float, lon: float, timeout_s: float = 4.0) -> dict:
    """Nearest-site PM2.5 reading; tries live AirQo, falls back to simulated data."""
    token = os.environ.get("AIRQO_API_TOKEN")
    if not token or not _HAS_REQUESTS:
        return _synthetic_air_quality(lat, lon)

    try:
        resp = requests.get(_AIRQO_MEASUREMENTS_URL, params={
            "latitude": lat, "longitude": lon, "token": token,
        }, timeout=timeout_s)
        resp.raise_for_status()
        data = resp.json()
        measurements = data.get("measurements", [])
        if not measurements:
            raise ValueError("Empty measurements in AirQo response.")
        pm25 = measurements[0].get("pm2_5", {}).get("value")
        if pm25 is None:
            raise ValueError("No pm2_5 value in AirQo response.")
        label, color = classify_aqi(pm25)
        return {
            "source": "AirQo (live)",
            "pm2_5": round(float(pm25), 1),
            "aqi_label": label,
            "aqi_color": color,
        }
    except Exception:  # noqa: BLE001 — any network/parse failure degrades to simulated data
        return _synthetic_air_quality(lat, lon)
