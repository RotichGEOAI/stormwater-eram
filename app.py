"""
ERAM-style Stormwater Infrastructure Tool for Kenyan Cities
============================================================
Evaluates green / hybrid / grey stormwater infrastructure across GIS zones
using LTHIA-LID + SCS-CN flood modeling (Hydrologic-Soil-Group aware),
lifecycle cost-benefit analysis, point/non-point pollutant loading,
flood-linked disease-risk screening, population-at-risk exposure,
watershed/riparian conservation priority, and air quality (AirQo/AfriqAir),
with interactive mapping, SSP-RCP climate scenarios, and a downloadable
PDF snapshot report.

Boundary data: drop Kenya ward shapefiles into data/shapefiles/ (see that
folder's README). The "Boundary Data" tab and the Ward Comparison tab both
cascade through whichever attribute columns you choose, in the order you
choose them — exactly like chaining "select by attribute" filters in
desktop GIS. Typically County -> Constituency -> Ward, but any columns,
any order, any number of levels. Loaded features are identified internally
by the full chain of values you selected (not just the last one), since a
bare final-level name is not always a safe unique key (e.g. many Kenyan
counties have a ward literally named "Township").
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from streamlit_folium import st_folium

from models import flood_prediction
from utils import (data_generator, scenario_builder, cost_benefit, gis_utils,
                    charts, pdf_report, pipeline, shapefile_loader,
                    climate_scenarios, disease_risk, watershed, air_quality_service)

st.set_page_config(page_title="Kenya ERAM Stormwater Tool", page_icon="🌍", layout="wide")

SCENARIO_ORDER = ["Grey", "Hybrid", "Green"]
SEVERITY_ORDER = ["None", "Low", "Moderate", "High", "Severe"]
SEVERITY_COLOR = {"Low": "#fdd835", "Moderate": "#fb8c00", "High": "#e53935", "Severe": "#8e0000"}

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------
if "loaded_wards" not in st.session_state:
    # unique_label -> {"zones_df", "bounds", "cascade_fields", "level_values", "final_value"}
    st.session_state.loaded_wards = {}
if "shapefile_gdf" not in st.session_state:
    st.session_state.shapefile_gdf = None
if "cascade_fields" not in st.session_state:
    st.session_state.cascade_fields = []   # ordered list of attribute columns to cascade through
if "cascade_compare_wards" not in st.session_state:
    st.session_state.cascade_compare_wards = []


def _cascade_label(level_values: list) -> str:
    """
    Composite identity built from the full chain of cascade values selected
    (not just the final level) — a bare final-level value is not always a
    safe unique key (e.g. many Kenyan counties have a ward literally named
    "Township"), so collapsing multiple attribute levels into one label
    keeps same-named features in different areas distinct.
    """
    values = [str(v) for v in level_values if v is not None]
    if not values:
        return "Unknown"
    if len(values) == 1:
        return values[0]
    return f"{values[-1]} — " + ", ".join(reversed(values[:-1]))


# ------------------------------------------------------------------
# Cached sample-data pipeline — recomputed only when the SSP/flavor changes
# ------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_base_zones() -> pd.DataFrame:
    return data_generator.generate_zones()


@st.cache_data(show_spinner=False)
def _run_sample_pipeline(ssp_key: str, flavor: str) -> pd.DataFrame:
    return pipeline.run_models(_load_base_zones(), ssp_key=ssp_key, climate_flavor=flavor)


# ------------------------------------------------------------------
# Sidebar — climate scenario (applies globally) + primary ward + layers
# ------------------------------------------------------------------
st.sidebar.header("🌍 ERAM Stormwater Tool")
st.sidebar.caption("Kenya · North Rift + Nairobi-metro sample wards")

st.sidebar.subheader("🌡️ Climate scenario")
ssp_key = st.sidebar.selectbox(
    "SSP-RCP pathway", climate_scenarios.SSP_ORDER,
    format_func=lambda k: f"{k} ({climate_scenarios.SSP_SCENARIOS[k]['label']})",
    index=2,
)
climate_flavor = st.sidebar.selectbox("Climate possibility", climate_scenarios.CLIMATE_FLAVOR_ORDER, index=2)
st.sidebar.caption(climate_scenarios.CLIMATE_FLAVORS[climate_flavor]["description"])

sample_df = _run_sample_pipeline(ssp_key, climate_flavor)

# Recompute any shapefile-loaded wards fresh each run under the current
# climate scenario (cheap — a handful of zones per ward, no caching needed).
loaded_frames = [
    pipeline.run_models(payload["zones_df"], ssp_key=ssp_key, climate_flavor=climate_flavor)
    for payload in st.session_state.loaded_wards.values()
]

full_df = pd.concat([sample_df] + loaded_frames, ignore_index=True) if loaded_frames else sample_df
full_df["Scenario"] = pd.Categorical(full_df["Scenario"], categories=SCENARIO_ORDER, ordered=True)
all_wards = sorted(full_df["Ward"].unique().tolist())
totals = charts.aggregate_costs_and_services(full_df)

if st.session_state.loaded_wards:
    st.sidebar.caption(f"📁 {len(st.session_state.loaded_wards)} boundary-file ward(s) loaded")

primary_ward = st.sidebar.selectbox("Primary ward", all_wards, index=0)
map_scenario = st.sidebar.select_slider("Scenario shown on map", options=SCENARIO_ORDER, value="Grey")

st.sidebar.markdown("---")
st.sidebar.subheader("Map layers")
show_rainfall = st.sidebar.checkbox("Rainfall intensity", value=True)
show_population_risk = st.sidebar.checkbox("Population at flood risk", value=True)
show_riparian = st.sidebar.checkbox("Riparian conservation buffers", value=False)
show_air_quality = st.sidebar.checkbox("Air quality (AirQo/AfriqAir)", value=False)

st.sidebar.markdown("---")
st.sidebar.subheader("Infographic layers")
show_capex = st.sidebar.checkbox("CAPEX", value=True)
show_opex = st.sidebar.checkbox("OPEX", value=True)
show_services = st.sidebar.checkbox("Co-benefits", value=True)

st.sidebar.markdown("---")
compare_wards = st.sidebar.multiselect("Quick compare (any wards)", all_wards, default=all_wards[:2])

st.title("🌍 ERAM Stormwater Infrastructure Tool — Kenya")
st.caption("Green vs. hybrid vs. grey infrastructure: flood modeling, lifecycle cost, pollutant "
           "loading, disease risk, population exposure, watershed/carbon priority, air quality, "
           "and climate scenarios by GIS zone.")

tab_boundary, tab_map, tab_scenario, tab_flood, tab_costs, tab_watershed, tab_compare, tab_report = st.tabs([
    "📁 Boundary Data", "🗺️ GIS & Flood Risk Map", "🔧 Scenario Builder", "🌊 Flood Prediction",
    "💰 Cost-Benefit Dashboard", "🌳 Watershed & Carbon", "📊 Ward Comparison", "📑 PDF Report",
])


def _cascade_picker(gdf, fields: list[str], key_prefix: str, multi_final: bool = False):
    """
    Cascades through an arbitrary ordered list of attribute columns — each
    level's options are filtered by every level picked before it, mirroring
    "select by attribute" chaining in desktop GIS. The column name itself
    is shown as the widget label, so the user sees exactly which attribute
    they're filtering on at each step.

    Returns (level_values, final_selection): level_values is the list of
    values picked at every level except the last (in order); final_selection
    is a single value (multi_final=False) or a list (multi_final=True) for
    the last field.
    """
    if not fields:
        return [], ([] if multi_final else None)

    filters: dict = {}
    level_values = []
    enabled = True
    for i, field in enumerate(fields[:-1]):
        options = shapefile_loader.list_values(gdf, field, filters=filters or None) if enabled else []
        val = st.selectbox(field, ["—"] + options, key=f"{key_prefix}_lvl{i}", disabled=not enabled)
        val = None if val == "—" else val
        level_values.append(val)
        filters[field] = val
        enabled = enabled and val is not None

    final_field = fields[-1]
    final_options = shapefile_loader.list_values(gdf, final_field, filters=filters or None) if enabled else []
    if multi_final:
        final_val = st.multiselect(final_field, final_options, key=f"{key_prefix}_final", disabled=not enabled)
    else:
        sel = st.selectbox(final_field, ["—"] + final_options, key=f"{key_prefix}_final", disabled=not enabled)
        final_val = None if sel == "—" else sel
    return level_values, final_val


def _load_feature(gdf, fields: list[str], level_values: list, final_value, zones_per_ward: int = 9) -> str:
    """Loads one selected feature into session state, keyed by the full cascade-value composite label."""
    filters = {f: v for f, v in zip(fields[:-1], level_values)}
    final_field = fields[-1]
    all_values = level_values + [final_value]
    seed = abs(hash("|".join(str(v) for v in all_values))) % 10000

    zones_df = shapefile_loader.generate_zones_within_ward(
        gdf, final_field, final_value, filters=filters, zones_per_ward=zones_per_ward, seed=seed)
    bounds, _ = shapefile_loader.ward_bounds(gdf, final_field, final_value, filters=filters)

    unique_label = _cascade_label(all_values)
    zones_df = zones_df.copy()
    zones_df["Ward"] = unique_label

    st.session_state.loaded_wards[unique_label] = {
        "zones_df": zones_df, "bounds": bounds,
        "cascade_fields": fields, "level_values": level_values, "final_value": final_value,
    }
    return unique_label


# ----------------------------------------------------------------------
# Tab 0 — Boundary data: server-side folder + County -> Constituency -> Ward cascade
# ----------------------------------------------------------------------
with tab_boundary:
    st.subheader("📁 Boundary data")
    st.caption("Drop shapefiles into `data/shapefiles/` on the server (see the README in that "
               "folder). No upload needed — the app scans that folder directly.")

    bundles = shapefile_loader.list_available_shapefiles()
    if not bundles:
        st.info("No shapefiles found in `data/shapefiles/`. Add a `.zip` bundle or a `.shp` + "
                 "its sibling files, then refresh this page.")
    else:
        labels = [b["label"] for b in bundles]
        chosen_label = st.selectbox("Boundary file", labels)
        chosen_path = next(b["path"] for b in bundles if b["label"] == chosen_label)

        if st.button("Load boundary file"):
            try:
                with st.spinner("Reading shapefile..."):
                    gdf = shapefile_loader.load_shapefile_from_path(chosen_path)
                st.session_state.shapefile_gdf = gdf
                attr_cols_guess = [c for c in gdf.columns if c != "geometry"]
                guessed = [
                    shapefile_loader.guess_county_column(gdf),
                    shapefile_loader.guess_constituency_column(gdf),
                    shapefile_loader.guess_ward_column(gdf),
                ]
                # de-dupe while preserving order, drop anything that didn't resolve to a real column
                seen = set()
                st.session_state.cascade_fields = [
                    c for c in guessed if c in attr_cols_guess and not (c in seen or seen.add(c))
                ]
                st.success(f"Loaded {len(gdf)} feature(s) from {chosen_label}.")
            except shapefile_loader.ShapefileLoadError as exc:
                st.error(str(exc))

    gdf = st.session_state.shapefile_gdf
    if gdf is not None:
        attr_cols = [c for c in gdf.columns if c != "geometry"]
        with st.expander("Attribute table", expanded=False):
            st.dataframe(gdf[attr_cols], use_container_width=True, hide_index=True)

        st.markdown("**Cascade fields** — pick any columns from the attribute table, in the order "
                     "you want to filter by (first = broadest, last = the specific feature you're "
                     "locating). Mirrors chaining 'select by attribute' in desktop GIS — not limited "
                     "to County/Constituency/Ward, and not limited to three levels.")
        default_fields = [f for f in st.session_state.cascade_fields if f in attr_cols]
        cascade_fields = st.multiselect("Cascade fields, in order", attr_cols, default=default_fields,
                                         key="cascade_fields_picker")
        st.session_state.cascade_fields = cascade_fields

        if not cascade_fields:
            st.info("Pick at least one field above to build the cascade (e.g. a Ward-name column "
                     "on its own, or County → Constituency → Ward for a full chain).")
        else:
            st.markdown("---")
            st.markdown("**Cascade by attribute:** " + " → ".join(cascade_fields))
            level_values, features_selected = _cascade_picker(gdf, cascade_fields,
                                                                key_prefix="main", multi_final=True)

            zones_per_ward = st.slider("Synthetic zones per feature", 3, 20, 9)

            if features_selected and st.button(f"Load {len(features_selected)} selected feature(s) into workspace",
                                                type="primary"):
                with st.spinner("Clipping zone grids and running models..."):
                    loaded_labels = [_load_feature(gdf, cascade_fields, level_values, f, zones_per_ward)
                                      for f in features_selected]
                st.success(f"Loaded: {', '.join(loaded_labels)}. Pick them from the ward dropdown in the sidebar.")
                st.rerun()

    if st.session_state.loaded_wards:
        st.markdown("---")
        st.markdown("**Loaded wards**")
        for name in list(st.session_state.loaded_wards.keys()):
            c1, c2 = st.columns([4, 1])
            c1.write(f"• {name}")
            if c2.button("Remove", key=f"remove_{name}"):
                del st.session_state.loaded_wards[name]
                st.rerun()

# ----------------------------------------------------------------------
# Tab 1 — Interactive map + population-at-risk + disease-risk + air quality
# ----------------------------------------------------------------------
with tab_map:
    st.subheader(f"📌 {primary_ward} — {map_scenario} scenario")
    zone_view = full_df[(full_df["Ward"] == primary_ward) & (full_df["Scenario"] == map_scenario)]

    if primary_ward in st.session_state.loaded_wards:
        bounds = st.session_state.loaded_wards[primary_ward]["bounds"]
    else:
        bounds = gis_utils.bounds_from_zones(zone_view)
    miny, minx, maxy, maxx = bounds
    center_lat, center_lon = (miny + maxy) / 2, (minx + maxx) / 2

    aq_reading = air_quality_service.get_air_quality(center_lat, center_lon) if show_air_quality else None

    col_map, col_stats = st.columns([2.4, 1])
    with col_map:
        fmap = gis_utils.build_map(zone_view, primary_ward, center_lat, center_lon,
                                    show_rainfall=show_rainfall, zoom_bounds=bounds,
                                    show_population_risk=show_population_risk,
                                    show_riparian=show_riparian,
                                    show_air_quality=show_air_quality, air_quality_reading=aq_reading)
        st_folium(fmap, width=None, height=520, returned_objects=[])
    with col_stats:
        st.metric("Zones mapped", len(zone_view))
        risk_counts = zone_view["FloodRisk"].value_counts()
        for risk in ["High", "Moderate", "Low"]:
            st.metric(f"{risk} risk zones", int(risk_counts.get(risk, 0)))
        st.metric("Total population", f"{int(zone_view['Population'].sum()):,}")
        st.metric("Est. population at flood risk", f"{int(zone_view['PopulationAtRisk'].sum()):,}")
        if show_air_quality and aq_reading:
            st.metric("PM2.5 (nearest site)", f"{aq_reading['pm2_5']} µg/m³", aq_reading["aqi_label"])
            st.caption(f"Source: {aq_reading['source']}")
        st.caption("Click any zone polygon for full runoff, cost, HSG, riparian, and disease-risk detail.")

    st.markdown("---")
    st.subheader("🦟 Flood-linked disease risk — ward summary")
    st.caption("Indicative screening only (WHO flood-health guidance patterns), weighted by each "
               "zone's flood-risk level and the sidebar's climate scenario — not a diagnostic or "
               "epidemiological forecast. Pair with local health-authority surveillance data.")
    disease_rows = []
    for row in zone_view.itertuples():
        for disease, severity in (row.DiseaseRisk or {}).items():
            disease_rows.append({"Zone": row.Zone, "Flood Risk": row.FloodRisk,
                                  "Disease": disease, "Severity": severity})
    if disease_rows:
        ddf = pd.DataFrame(disease_rows)
        ddf["_severity_rank"] = ddf["Severity"].map(SEVERITY_ORDER.index)
        worst = (ddf.sort_values("_severity_rank", ascending=False)
                 .groupby("Disease", as_index=False).first()
                 .sort_values("_severity_rank", ascending=False))
        for _, r in worst.iterrows():
            color = SEVERITY_COLOR.get(r["Severity"], "#888")
            st.markdown(f"<span style='color:{color}; font-weight:bold;'>● {r['Disease']}</span> — "
                        f"{r['Severity']} (worst at {r['Zone']}, {r['Flood Risk']} flood risk)",
                        unsafe_allow_html=True)
    else:
        st.write("No elevated disease risk flagged for this ward/scenario.")

# ----------------------------------------------------------------------
# Tab 2 — Manual scenario builder (single what-if zone) + SSP framing
# ----------------------------------------------------------------------
with tab_scenario:
    st.subheader("🔧 Build a custom what-if scenario")
    st.info(climate_scenarios.recommend_infrastructure_mix(ssp_key, climate_flavor))

    c1, c2, c3 = st.columns(3)
    with c1:
        land_use = st.selectbox("Land use", data_generator.LAND_USES)
        scenario_type = st.selectbox("Infrastructure scenario", SCENARIO_ORDER, index=2)
    with c2:
        impervious_surface = st.slider("Impervious surface (%)", 0, 100, 45)
        population = st.number_input("Population served", min_value=100, value=5000, step=100)
    with c3:
        rainfall = st.number_input("Design storm rainfall (mm)", min_value=0.0, value=80.0, step=5.0)
        hsg = st.selectbox("Hydrologic Soil Group", ["A", "B", "C", "D"], index=2)

    scenario = scenario_builder.build_scenario(land_use, impervious_surface, population, rainfall, scenario_type)
    flood = flood_prediction.predict(land_use, impervious_surface, rainfall, scenario_type, hsg)
    econ = cost_benefit.analyze(scenario_type, population, rainfall, impervious_surface)
    diseases = disease_risk.assess_disease_risk(flood["flood_risk"], climate_flavor)

    st.markdown(f"**Approach:** {scenario['description']}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Avg. runoff", f"{flood['average_runoff_mm']} mm")
    m2.metric("Flood risk", flood["flood_risk"])
    m3.metric("Peak attenuation", f"{flood['peak_attenuation_pct']}%")
    m4.metric("CAPEX", f"${econ['CAPEX_USD']:,.0f}")

    if diseases:
        st.markdown("**Flood-linked disease risk:** " +
                     ", ".join(f"{d} ({s})" for d, s in diseases.items()))

    with st.expander("Full model output"):
        st.json({"scenario": scenario, "flood_prediction": flood, "cost_benefit": econ,
                 "disease_risk": diseases})

# ----------------------------------------------------------------------
# Tab 3 — Flood prediction + pollutant loading detail table
# ----------------------------------------------------------------------
with tab_flood:
    st.subheader(f"🌊 LTHIA-LID vs. SCS-CN — {primary_ward}")
    st.caption("Both models use the zone's Hydrologic Soil Group (HSG) — a SoilGrids/AfSIS-style "
               "proxy here (SSURGO itself only covers the US, so isn't applicable to Kenya).")
    flood_table = full_df[full_df["Ward"] == primary_ward][
        ["Zone", "LandUse", "HSG", "ImperviousSurface", "Scenario", "MeanRainfall_mm",
         "LTHIA_Runoff_mm", "SCS_Runoff_mm", "Average_Runoff_mm", "Peak_Attenuation_pct", "FloodRisk"]
    ].sort_values(["Zone", "Scenario"])
    st.dataframe(flood_table, use_container_width=True, hide_index=True)

    st.markdown("### 👥 Population exposure by flood risk")
    pop_table = full_df[(full_df["Ward"] == primary_ward) & (full_df["Scenario"] == map_scenario)][
        ["Zone", "FloodRisk", "Population", "PopulationAtRisk"]
    ].sort_values("PopulationAtRisk", ascending=False)
    st.dataframe(pop_table, use_container_width=True, hide_index=True)
    st.caption("Population-at-risk uses a planning-level exposure share by flood-risk band "
               "(Low 5% / Moderate 25% / High 55%) — a proxy for likely-affected population, "
               "not a hydraulic inundation-extent model.")

    st.markdown("### 🧪 Point & non-point source pollutant loading")
    st.caption("Non-point source load = runoff volume × event mean concentration by land use; "
               "point-source zones add a fixed annual discharge load. Treatment efficiency scales "
               "with the infrastructure scenario (Green > Hybrid > Grey).")
    pollutant_table = full_df[full_df["Ward"] == primary_ward][
        ["Zone", "Scenario", "PointSource", "TSS_kg", "TN_kg", "TP_kg", "FecalColiform_index"]
    ].sort_values(["Zone", "Scenario"])
    st.dataframe(pollutant_table, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------
# Tab 4 — Cost-benefit dashboard
# ----------------------------------------------------------------------
with tab_costs:
    st.subheader(f"💰 Lifecycle Cost & Co-benefits — {primary_ward}")
    st.caption(f"Rainfall inputs reflect {ssp_key} ({climate_scenarios.SSP_SCENARIOS[ssp_key]['label']}) "
               f"under {climate_flavor.lower()} conditions.")
    fig = charts.scenario_comparison_figure(totals, primary_ward)
    if not show_capex:
        fig.data = [t for t in fig.data if t.name != "CAPEX (USD)"]
    if not show_opex:
        fig.data = [t for t in fig.data if t.name != "OPEX (USD)"]
    if not show_services:
        fig.data = [t for t in fig.data if "yaxis2" not in (t.yaxis or "")]
    st.plotly_chart(fig, use_container_width=True)

    econ_table = full_df[full_df["Ward"] == primary_ward][
        ["Zone", "Scenario", "CAPEX_USD", "OPEX_USD", "NPV_USD", "BCR", "Payback_Years",
         "Carbon_Sequestration", "Urban_Cooling", "Biodiversity_Index"]
    ].sort_values(["Zone", "Scenario"])
    st.dataframe(econ_table, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Download zone data (CSV)", econ_table.to_csv(index=False),
                        file_name=f"{primary_ward.replace(' ', '_').replace(',', '')}_cost_benefit.csv",
                        mime="text/csv")

# ----------------------------------------------------------------------
# Tab 5 — Watershed, riparian conservation & carbon sequestration priority
# ----------------------------------------------------------------------
with tab_watershed:
    st.subheader(f"🌳 Watershed, riparian conservation & carbon priority — {primary_ward}")
    st.caption(
        "Indicative drainage-basin assignment and riparian buffers from a small set of major "
        "Kenyan rivers shipped with this app (simplified polylines — **not** survey-grade "
        "hydrography; see `utils/watershed.py`). Swap in a real HydroRIVERS or Water Resources "
        "Authority Kenya rivers layer for production use. Carbon-sequestration priority favors "
        "riparian-corridor zones, since protecting/revegetating riparian buffers is one of the "
        "most cost-effective levers for both carbon sequestration and biodiversity conservation."
    )
    ws_view = full_df[(full_df["Ward"] == primary_ward) & (full_df["Scenario"] == map_scenario)]

    w1, w2, w3 = st.columns(3)
    w1.metric("Basin(s) present", ", ".join(sorted(ws_view["Basin"].unique())))
    w2.metric("Riparian candidate zones", int(ws_view["RiparianZoneCandidate"].sum()))
    w3.metric("Avg. carbon priority score", f"{ws_view['CarbonPriorityScore'].mean():.1f}/100")

    ws_table = ws_view[["Zone", "LandUse", "NearestRiver", "Basin", "DistanceToRiver_km",
                         "RiparianZoneCandidate", "CarbonPriorityScore", "Carbon_Sequestration"]
                        ].sort_values("CarbonPriorityScore", ascending=False)
    st.dataframe(ws_table, use_container_width=True, hide_index=True)

    st.markdown("#### Rivers & basins shipped with this app")
    rivers_gdf = watershed.rivers_geodataframe()
    st.dataframe(rivers_gdf.drop(columns="geometry"), use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------
# Tab 6 — Multi-ward comparison: quick compare + up-to-4 cross-county cascade
# ----------------------------------------------------------------------
with tab_compare:
    st.subheader("📊 Cross-ward comparison")

    st.markdown("#### Quick compare (sidebar selection)")
    if len(compare_wards) < 2:
        st.info("Select at least two wards in the sidebar's 'Quick compare' box to compare.")
    else:
        metric = st.selectbox("Metric", ["CAPEX_USD", "OPEX_USD", "NPV_USD",
                                          "Carbon_Sequestration", "Urban_Cooling", "Biodiversity_Index",
                                          "CarbonPriorityScore"],
                               key="quick_compare_metric")
        st.plotly_chart(charts.multiward_comparison_figure(totals, compare_wards, metric),
                         use_container_width=True)

    st.markdown("---")
    st.markdown("#### Cascade-based comparison — up to 4 features, any combination")
    st.caption("Each of the four slots below runs its own independent cascade through the same "
               "attribute fields chosen in the 'Boundary Data' tab (in the same order), so you can "
               "pull one feature per slot from anywhere in the table — e.g. four different counties. "
               "Loaded features are tracked by the full chain of values selected, so same-named "
               "features in different areas (common in Kenya — many counties have a ward literally "
               "named \"Township\") never get confused with each other.")
    gdf = st.session_state.shapefile_gdf
    cascade_fields = st.session_state.cascade_fields
    if gdf is None or not cascade_fields:
        st.info("Load a boundary file and pick at least one cascade field in the 'Boundary Data' tab "
                 "first — each comparison slot below reuses that same field order.")
    else:
        slot_cols = st.columns(4)
        slot_selections = []
        for i, col in enumerate(slot_cols):
            with col:
                st.markdown(f"**Slot {i + 1}**")
                level_values, final_value = _cascade_picker(gdf, cascade_fields,
                                                              key_prefix=f"slot{i}", multi_final=False)
                slot_selections.append((level_values, final_value))

        if st.button("Compare selected wards", type="primary"):
            chosen = [(lv, fv) for lv, fv in slot_selections if fv]
            if len(chosen) < 2:
                st.warning("Pick at least two features across the slots above.")
            else:
                with st.spinner("Loading and modeling selected features..."):
                    labels = []
                    for level_values, final_value in chosen:
                        label = _cascade_label(level_values + [final_value])
                        if label not in st.session_state.loaded_wards:
                            label = _load_feature(gdf, cascade_fields, level_values, final_value)
                        labels.append(label)
                st.session_state.cascade_compare_wards = labels
                st.rerun()

        cascade_wards = [w for w in st.session_state.cascade_compare_wards if w in all_wards]
        if cascade_wards:
            st.success(f"Comparing: {', '.join(cascade_wards)}")
            metric2 = st.selectbox("Metric", ["CAPEX_USD", "OPEX_USD", "NPV_USD",
                                               "Carbon_Sequestration", "Urban_Cooling", "Biodiversity_Index",
                                               "CarbonPriorityScore"],
                                    key="cascade_compare_metric")
            st.plotly_chart(charts.multiward_comparison_figure(totals, cascade_wards, metric2),
                             use_container_width=True)

            pop_summary = (full_df[full_df["Ward"].isin(cascade_wards) & (full_df["Scenario"] == "Grey")]
                           .groupby("Ward", as_index=False)[["Population", "PopulationAtRisk"]].sum())
            st.markdown("**Population exposure by ward**")
            st.dataframe(pop_summary, use_container_width=True, hide_index=True)

            st.dataframe(totals[totals["Ward"].isin(cascade_wards)], use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------
# Tab 7 — PDF export
# ----------------------------------------------------------------------
with tab_report:
    st.subheader("📑 Export a PDF snapshot")
    report_wards = compare_wards if len(compare_wards) >= 2 else [primary_ward]
    st.write(f"Report scope: **{', '.join(report_wards)}**")
    if st.button("Generate PDF"):
        with st.spinner("Building report..."):
            pdf_bytes = pdf_report.build_pdf(full_df, totals, report_wards)
        st.success("Report ready.")
        st.download_button("⬇️ Download PDF", pdf_bytes,
                            file_name=f"{report_wards[0].replace(' ', '_').replace(',', '')}_eram_snapshot.pdf",
                            mime="application/pdf")
