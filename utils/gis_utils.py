"""
Interactive map builder. Renders zone polygons colored by flood risk, with
click/hover popups showing full runoff/HSG/pollutant/disease-risk stats,
optional layers for rainfall intensity, population-at-risk, riparian
conservation buffers, and air-quality monitoring points.
"""

from __future__ import annotations
import folium
from folium.plugins import HeatMap

RISK_COLORS = {"Low": "#2e7d32", "Moderate": "#f9a825", "High": "#c62828"}


def bounds_from_zones(zones_df):
    """(miny, minx, maxy, maxx) spanning every zone geometry — works for any ward, sample or uploaded."""
    all_bounds = [g.bounds for g in zones_df.geometry]  # (minx, miny, maxx, maxy) each
    minx = min(b[0] for b in all_bounds)
    miny = min(b[1] for b in all_bounds)
    maxx = max(b[2] for b in all_bounds)
    maxy = max(b[3] for b in all_bounds)
    return miny, minx, maxy, maxx


def _population_radius(pop_at_risk: int) -> float:
    """Marker radius (px) scaled to population at risk, floor/ceiling so tiny/huge values stay legible."""
    return max(6, min(28, 6 + (pop_at_risk ** 0.5) * 0.9))


def build_map(zones_df, ward: str, center_lat: float, center_lon: float,
              show_rainfall: bool = True, zoom_bounds=None,
              show_population_risk: bool = False, show_riparian: bool = False,
              show_air_quality: bool = False, air_quality_reading: dict | None = None) -> folium.Map:
    """
    Build a Folium map for one ward: rainfall heatmap + clickable risk zones,
    with optional population-at-risk, riparian-buffer, and air-quality layers.
    Pass zoom_bounds=(miny, minx, maxy, maxx) to fit the view to an exact
    boundary (e.g. a shapefile-loaded ward polygon) instead of a fixed zoom.
    """
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=15, tiles="cartodbpositron")
    if zoom_bounds is not None:
        miny, minx, maxy, maxx = zoom_bounds
        fmap.fit_bounds([[miny, minx], [maxy, maxx]])

    if show_rainfall and not zones_df.empty:
        heat_points = [
            [row.lat, row.lon, max(row.MeanRainfall_mm, 1)]
            for row in zones_df.itertuples()
        ]
        HeatMap(heat_points, name="Rainfall intensity", radius=45, blur=35,
                min_opacity=0.25, max_zoom=17).add_to(fmap)

    zone_layer = folium.FeatureGroup(name="Zones (flood risk)")
    for row in zones_df.itertuples():
        risk = getattr(row, "FloodRisk", "Low")
        color = RISK_COLORS.get(risk, "#1565c0")
        diseases = getattr(row, "DiseaseRisk", {}) or {}
        disease_html = "".join(f"{d}: <b>{s}</b><br>" for d, s in diseases.items()) or "None flagged<br>"
        pop = getattr(row, "Population", None)
        pop_at_risk = getattr(row, "PopulationAtRisk", None)
        pop_html = (f"<b>Population:</b> {pop:,} &nbsp;|&nbsp; <b>Est. at risk:</b> {pop_at_risk:,}<br>"
                    if pop is not None and pop_at_risk is not None else "")
        riparian_html = (f"<b>Riparian candidate zone:</b> {'Yes — near ' + str(getattr(row, 'NearestRiver', '?')) if getattr(row, 'RiparianZoneCandidate', False) else 'No'} "
                          f"({getattr(row, 'DistanceToRiver_km', '—')} km to nearest river, {getattr(row, 'Basin', '—')})<br>"
                          f"<b>Carbon sequestration priority:</b> {getattr(row, 'CarbonPriorityScore', '—')}/100<br>")
        popup_html = f"""
        <div style="font-family: sans-serif; font-size: 13px;">
        <b>Zone:</b> {row.Zone}<br>
        <b>Land use:</b> {row.LandUse} &nbsp;|&nbsp; <b>HSG:</b> {getattr(row, 'HSG', '—')}<br>
        <b>Impervious surface:</b> {row.ImperviousSurface}%<br>
        {pop_html}
        <b>Design rainfall:</b> {row.MeanRainfall_mm} mm<br>
        <b>LTHIA runoff:</b> {getattr(row, 'LTHIA_Runoff_mm', '—')} mm<br>
        <b>SCS runoff:</b> {getattr(row, 'SCS_Runoff_mm', '—')} mm<br>
        <b>Avg. runoff:</b> {getattr(row, 'Average_Runoff_mm', '—')} mm<br>
        <b>Peak attenuation:</b> {getattr(row, 'Peak_Attenuation_pct', '—')}%<br>
        <b>Flood risk:</b> <span style="color:{color}; font-weight:bold;">{risk}</span><br>
        <b>Scenario:</b> {getattr(row, 'Scenario', '—')}<br>
        <hr style="margin:4px 0;">
        {riparian_html}
        <hr style="margin:4px 0;">
        <b>Flood-linked disease risk:</b><br>{disease_html}
        </div>
        """
        coords = list(row.geometry.exterior.coords)
        latlon_coords = [(lat, lon) for lon, lat in coords]
        folium.Polygon(
            locations=latlon_coords,
            color="black", weight=1, fill=True,
            fill_color=color, fill_opacity=0.55,
            tooltip=f"{row.Zone} — {risk} risk",
            popup=folium.Popup(popup_html, max_width=300),
        ).add_to(zone_layer)
    zone_layer.add_to(fmap)

    if show_population_risk and not zones_df.empty and "PopulationAtRisk" in zones_df.columns:
        pop_layer = folium.FeatureGroup(name="Population at flood risk")
        for row in zones_df.itertuples():
            risk = getattr(row, "FloodRisk", "Low")
            pop_at_risk = getattr(row, "PopulationAtRisk", 0)
            if pop_at_risk <= 0:
                continue
            folium.CircleMarker(
                location=[row.lat, row.lon],
                radius=_population_radius(pop_at_risk),
                color="#4a148c", weight=1.5, fill=True,
                fill_color=RISK_COLORS.get(risk, "#4a148c"), fill_opacity=0.6,
                tooltip=f"{row.Zone}: ~{pop_at_risk:,} people at risk ({risk} flood risk)",
            ).add_to(pop_layer)
        pop_layer.add_to(fmap)

    if show_riparian:
        from . import watershed
        riparian_layer = folium.FeatureGroup(name="Riparian conservation buffers")
        buffers = watershed.riparian_buffers()
        for row in buffers.itertuples():
            geom = row.geometry
            polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
            for poly in polys:
                latlon = [(lat, lon) for lon, lat in poly.exterior.coords]
                folium.Polygon(
                    locations=latlon, color="#00695c", weight=1,
                    fill=True, fill_color="#00897b", fill_opacity=0.25,
                    tooltip=f"{row.River} riparian buffer ({row.buffer_m} m) — {row.Basin}",
                ).add_to(riparian_layer)
        riparian_layer.add_to(fmap)

    if show_air_quality and air_quality_reading is not None:
        aq_layer = folium.FeatureGroup(name="Air quality (AirQo/AfriqAir)")
        folium.CircleMarker(
            location=[center_lat, center_lon], radius=14,
            color="black", weight=1, fill=True,
            fill_color=air_quality_reading.get("aqi_color", "#888"), fill_opacity=0.85,
            tooltip=(f"PM2.5 ≈ {air_quality_reading.get('pm2_5', '—')} µg/m³ "
                     f"— {air_quality_reading.get('aqi_label', '—')} ({air_quality_reading.get('source', '—')})"),
        ).add_to(aq_layer)
        aq_layer.add_to(fmap)

    legend_html = """
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
                background: white; padding: 10px 14px; border-radius: 6px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 12px; font-family: sans-serif;">
      <b>Flood risk</b><br>
      <span style="color:#2e7d32;">●</span> Low&nbsp;&nbsp;
      <span style="color:#f9a825;">●</span> Moderate&nbsp;&nbsp;
      <span style="color:#c62828;">●</span> High
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap
