"""
Real-time and forecast rainfall for a given lat/lon.

Uses Open-Meteo (https://open-meteo.com) as the default live source — it's
free, keyless, and blends multiple meteorological models (ECMWF, GFS,
ICON, etc.) plus recent observations, which is a reasonable practical
stand-in for "satellites and models" without needing API credentials.
True satellite precipitation products (CHIRPS, NASA IMERG/GPM) would need
a Google Earth Engine or NASA Earthdata integration — swap the fetch
function below for that if you have access.

This sandbox's own network policy blocks arbitrary outbound API calls, so
the live path can't be exercised from here — but it degrades safely: any
network failure (no route, timeout, non-200 response) falls back to a
seeded synthetic rainfall series so the rest of the app keeps working.
"""

from __future__ import annotations
import numpy as np

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _synthetic_rainfall(lat: float, lon: float, forecast_days: int = 7) -> dict:
    """Deterministic fallback series, seeded on location so repeated calls are stable."""
    seed = int(abs(lat * 1000) + abs(lon * 1000))
    rng = np.random.default_rng(seed)
    realtime_mm_today = round(float(rng.uniform(0, 25)), 1)
    forecast = [round(float(rng.uniform(0, 30)), 1) for _ in range(forecast_days)]
    return {
        "source": "simulated (offline fallback)",
        "realtime_mm_today": realtime_mm_today,
        "forecast_mm_by_day": forecast,
        "forecast_total_mm": round(sum(forecast), 1),
    }


def get_rainfall(lat: float, lon: float, forecast_days: int = 7, timeout_s: float = 4.0) -> dict:
    """Realtime + forecast rainfall; tries Open-Meteo live, falls back to simulated data."""
    if not _HAS_REQUESTS:
        return _synthetic_rainfall(lat, lon, forecast_days)

    try:
        resp = requests.get(_OPEN_METEO_URL, params={
            "latitude": lat, "longitude": lon,
            "daily": "precipitation_sum",
            "past_days": 1,
            "forecast_days": forecast_days,
            "timezone": "auto",
        }, timeout=timeout_s)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        precip = daily.get("precipitation_sum", [])
        if not precip:
            raise ValueError("Empty precipitation series in Open-Meteo response.")

        realtime = precip[0]
        forecast = precip[1:1 + forecast_days]
        return {
            "source": "Open-Meteo (live, multi-model blend)",
            "realtime_mm_today": round(float(realtime), 1),
            "forecast_mm_by_day": [round(float(v), 1) for v in forecast],
            "forecast_total_mm": round(float(sum(forecast)), 1),
        }
    except Exception:  # noqa: BLE001 — any network/parse failure degrades to simulated data
        return _synthetic_rainfall(lat, lon, forecast_days)
