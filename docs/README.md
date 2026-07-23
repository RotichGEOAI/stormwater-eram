# ERAM Stormwater Infrastructure Tool — Kenya

Evaluates **green**, **hybrid**, and **grey** stormwater infrastructure for
Kenyan wards using lifecycle cost analysis, flood-risk modeling, pollutant
loading, flood-linked disease-risk screening, population-at-risk exposure,
watershed/riparian conservation priority, air quality, and SSP-RCP climate
scenarios.

Sample data ships pre-loaded for six wards (Eldoret/Kapsoya, Eldoret/Kimumu,
Kapsabet Town, Iten, Kahawa Wendani, Ruiru) so the app is fully explorable
with no setup required. Drop real IEBC/KNBS ward shapefiles into
`data/shapefiles/` for the real thing (see that folder's README).

## Features

- **Fully generalized cascade by attribute** — no longer limited to a fixed
  County→Constituency→Ward mapping. In the "Boundary Data" tab, pick *any*
  columns from the attribute table, in *any* order and *any* number of
  levels (e.g. Region → County → Constituency → Ward, or just Ward on its
  own, or something entirely different) — each level's dropdown filters to
  only the values consistent with everything picked before it, mirroring
  "select by attribute" chaining in desktop GIS. Auto-detection still
  pre-fills a sensible County/Constituency/Ward default (including GADM's
  `NAME_1`/`NAME_2`/`NAME_3` convention) — you're free to add, remove, or
  reorder fields from there.
- **4-way cross-county comparison** — the Ward Comparison tab has four
  *independent* cascades, each using the same field order chosen in
  Boundary Data, so you can pull one feature per slot from anywhere in the
  table — e.g. four different counties. Loaded features are tracked
  internally by the **full chain of cascade values**, not a bare final-level
  name — Kenya has ~1,450 wards and many counties share ward names (e.g.
  several counties each have a ward literally called "Township"), so a
  bare-name key would silently conflate different wards. This was a real
  bug in an earlier version and is now covered by a test that deliberately
  loads three different counties' "Township" wards side by side (via a
  4-level cascade, including a non-standard extra "Region" field) and
  asserts they stay distinct. A manual field-order change made in Boundary
  Data now also persists correctly into the Ward Comparison cascade (an
  earlier version kept a fixed 3-column mapping only locally, so
  corrections there didn't reach Ward Comparison).
- **GIS mapping** — interactive Folium map with toggleable layers: rainfall
  heatmap, population-at-flood-risk markers (sized/colored by exposure),
  riparian conservation buffers, and an air-quality marker, plus clickable
  zone polygons colored by flood risk with a popup showing full
  runoff/cost/HSG/pollutant/riparian/disease-risk detail.
- **Population-at-risk exposure** — each zone's population is split into an
  estimated at-risk share by flood-risk band (Low 5% / Moderate 25% / High
  55%) — a planning-level exposure proxy, not a hydraulic inundation-extent
  model. Shown as a ward-level total, a per-zone table, and a sized/colored
  map layer.
- **Watershed & riparian conservation / carbon priority** — a new tab
  assigns each zone to its nearest major Kenyan river/drainage basin, flags
  candidate riparian conservation zones, and scores each zone's carbon-
  sequestration priority (riparian corridors score highest, since protecting
  or revegetating them is one of the most cost-effective levers for both
  carbon sequestration and biodiversity). Ships with a small set of major
  Kenyan rivers (Nzoia, Yala, Nyando, Sondu-Miriu, Kerio, Turkwel plus Athi
  and Tana for national reference) as simplified indicative polylines —
  **not** survey-grade hydrography (no live Water Resources Authority Kenya
  or HydroSHEDS/HydroRIVERS feed is reachable from this environment). Swap
  in a real rivers shapefile in `utils/watershed.py` for production use.
- **Air quality (AirQo / AfriqAir)** — `utils/air_quality_service.py` calls
  AirQo's public measurements API (needs a free token from
  https://docs.airqo.net, set as the `AIRQO_API_TOKEN` environment
  variable/Streamlit secret) for a PM2.5 reading near the ward's centroid,
  with AQI-style banding. AfriqAir is a pan-African coordinating network
  of monitoring initiatives rather than a single queryable API, so it's
  credited as context rather than a second live endpoint. Falls back to a
  seeded synthetic reading if no token is set or the network call fails —
  this sandbox has no token and can't reach arbitrary hosts, so the live
  path is untested here; wire in a real token to exercise it.
- **Flood-linked disease-risk screening** — a rules-based screen (WHO
  flood-health guidance patterns: cholera, diarrheal disease, typhoid,
  malaria, leptospirosis, schistosomiasis, Rift Valley Fever) weighted by
  each zone's flood-risk level and the selected climate flavor. Indicative
  planning/awareness tool, **not** a diagnostic or epidemiological forecast.
- **SSP-RCP climate scenarios** — SSP1-1.9 through SSP5-8.5, each paired with
  a Wet/Dry/Warm/Hot climate-flavor modifier, adjusts the rainfall driving
  every flood/cost-benefit run and shapes an infrastructure-mix
  recommendation. Deltas are indicative East-Africa order-of-magnitude
  figures in the spirit of IPCC AR6 regional patterns — not a downscaled
  projection for a specific site (swap in real CMIP6/CORDEX-Africa deltas in
  `utils/climate_scenarios.py` if you have them).
- **Soil Hydrologic Group (HSG)** — both flood models use the standard NRCS
  TR-55 land-use × HSG curve-number table. **SSURGO itself is a US/NRCS
  product and doesn't cover Kenya** — this ships a texture→HSG proxy
  assigner instead, with a documented extension point
  (`utils/soil_hydrology.hsg_from_texture()`) to wire in real ISRIC
  SoilGrids or AfSIS texture data per zone.
- **Land-cover-based imperviousness proxy** — in the absence of a true
  impervious-surface raster, imperviousness is estimated from an ESA
  WorldCover/Esri Living Atlas-style land-cover class lookup
  (`utils/landcover_proxy.py`). Swap `sample_landcover()` for a real
  Sentinel-2/Living Atlas raster or Earth Engine query for production use.
- **Point & non-point source pollution** — TSS/TN/TP/fecal-coliform loading
  per zone via the event-mean-concentration method (the same approach
  LTHIA itself uses for water quality, not just flood depth), plus a fixed
  additive load for zones flagged with a point-source discharge. Treatment
  efficiency scales with the infrastructure scenario.
- **Real-time + forecast rainfall** — `utils/rainfall_service.py` calls
  Open-Meteo (free, keyless, blends multiple weather models) for live and
  7-day-forecast rainfall, with a seeded synthetic fallback if the network
  call fails — true satellite products (CHIRPS, NASA IMERG/GPM) would need
  a Google Earth Engine/NASA Earthdata integration.
- **Lifecycle cost-benefit** — CAPEX/OPEX, 20-year NPV, benefit-cost ratio,
  payback period, and carbon/cooling/biodiversity co-benefit indices.
- **PDF snapshot report** — infographic, executive summary, zone-level
  recommendations, and an implementation timeline, all downloadable.

## Architecture

```
stormwater-eram/
├── app.py                     # Streamlit UI — 8 tabs, cascading selectors, cached pipeline
├── requirements.txt
├── data/shapefiles/           # Drop Kenya ward shapefiles here (see its own README)
├── models/
│   ├── lthia_lid.py           # LTHIA-LID runoff model (HSG-aware, LID credit)
│   ├── scs_curve.py           # Independent SCS-CN runoff cross-check (HSG-aware)
│   └── flood_prediction.py    # Combines both models into a risk classification
├── utils/
│   ├── data_generator.py      # Synthetic ward/zone/rainfall sample data
│   ├── shapefile_loader.py    # Folder scanning, County/Constituency/Ward cascade, zone clipping
│   ├── soil_hydrology.py      # Hydrologic Soil Group + NRCS TR-55 CN lookup (SSURGO-equivalent)
│   ├── landcover_proxy.py     # Land-cover → imperviousness proxy (Sentinel/Living Atlas stand-in)
│   ├── rainfall_service.py    # Open-Meteo realtime + forecast rainfall, offline fallback
│   ├── air_quality_service.py # AirQo (+AfriqAir context) PM2.5/AQI, offline fallback
│   ├── pollutant_loading.py   # Point + non-point source pollutant loads (EMC method)
│   ├── disease_risk.py        # Flood-risk × climate → disease-risk screening
│   ├── watershed.py           # Kenya river/basin proxy, riparian buffers, carbon priority
│   ├── climate_scenarios.py   # SSP-RCP × Wet/Dry/Warm/Hot rainfall/temp adjustment
│   ├── scenario_builder.py    # Scenario record assembly
│   ├── cost_benefit.py        # CAPEX/OPEX/NPV/BCR/payback + co-benefit scoring
│   ├── gis_utils.py           # Folium map: risk polygons + rainfall/population/riparian/AQ layers
│   ├── pipeline.py            # Shared model runner (sample & shapefile-loaded wards alike)
│   ├── charts.py               # Plotly dashboard charts + matplotlib PDF charts
│   └── pdf_report.py           # reportlab PDF assembly
└── docs/README.md
```

## Design notes / honest limitations

- **Feature identity is the full cascade-value composite**, not a bare
  final-level name — see the "4-way cross-county comparison" note above.
  This matters anywhere Kenyan ward data is involved; a bare-name key will
  silently misattribute data between same-named features in different
  areas.
- **No GDAL/rasterio dependency for geometry.** Zone geometries use
  `shapely`/`geopandas` directly.
- **Two-layer caching.** `st.cache_data` separates raw zone generation from
  the flood/cost-benefit model run (keyed on the SSP/climate-flavor
  selection), so switching tabs or toggling display options doesn't
  recompute the model matrix. Shapefile-loaded wards are re-run each time
  (cheap — a handful of zones per ward) so they stay in sync with the
  sidebar's climate scenario.
- **SSURGO does not cover Kenya.** It's a US-only NRCS database. Hydrologic
  Soil Group is estimated via a documented proxy instead — real coverage
  would come from ISRIC SoilGrids (global, includes Kenya) or AfSIS.
- **Sentinel/Living Atlas imperviousness is a lookup-table proxy**, not a
  live raster query — this sandbox has no credentials/network access to
  Copernicus, Earth Engine, or ArcGIS Living Atlas.
- **River/basin data is a small indicative set**, not survey-grade
  hydrography — no live WRA Kenya or HydroSHEDS/HydroRIVERS feed is
  reachable here. The riparian-buffer "candidate zone" flag uses a generous
  tolerance around the simplified polylines and is meant for ground-truthing
  and prioritization, not a legal riparian-setback determination.
- **AirQo integration needs a free API token** (`AIRQO_API_TOKEN`) to go
  live; AfriqAir is credited as a coordinating network rather than wired in
  as a second endpoint, since it isn't itself a single queryable API.
- **Rainfall forecast tries live Open-Meteo, falls back to simulated data**
  if the network call fails — keeps the app usable everywhere without
  silently showing wrong numbers as if they were live.
- **Climate-scenario deltas are indicative**, not a downscaled CMIP6/CORDEX
  projection for a specific site.
- **Disease-risk and population-at-risk are planning/awareness tools**, not
  diagnostic, epidemiological, or hydraulic-inundation models — always pair
  with local authority data.

## Running locally

```bash
cd stormwater-eram
pip install -r requirements.txt
# optional, to enable live AirQo air-quality data:
export AIRQO_API_TOKEN=your_token_here
streamlit run app.py
```

## Using your own GIS data

Drop a shapefile bundle (`.zip`, or `.shp` + `.shx` + `.dbf` + `.prj` with
matching names) into `data/shapefiles/`. Refresh the app, open the
**Boundary Data** tab, load the file, and pick your cascade fields (any
columns, any order, any number of levels — County/Constituency/Ward is
pre-filled as a sensible default when detectable). Cascade down to the
feature(s) you want. Everything downstream (map, flood prediction,
cost-benefit, watershed/carbon, PDF report, and the 4-way comparison) picks
it up automatically through the shared `utils/pipeline.py`.
