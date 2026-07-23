# Drop shapefiles here

Place Kenya administrative-boundary shapefiles in this folder as either:

- a single `.zip` containing the full bundle (`.shp` + `.shx` + `.dbf` + `.prj`,
  optionally a world file `.wld`/`.tfw`), or
- the loose files together (same base filename, e.g. `kenya_wards.shp`,
  `kenya_wards.shx`, `kenya_wards.dbf`, `kenya_wards.prj`).

The app scans this folder on startup and lists every bundle it finds in the
"Boundary Data" tab. Ideally the attribute table includes columns for
**County**, **Constituency**, and **Ward** (IEBC/KNBS naming varies — e.g.
`COUNTY_NAM`, `CONST_NAME`, `WARD_NAME` — the app tries to auto-detect them,
and lets you override the column mapping if the guess is wrong).

Subfolders are also scanned one level deep, so you can keep multiple sources
organized, e.g.:

```
data/shapefiles/
├── iebc_wards_2022/
│   ├── iebc_wards_2022.shp
│   ├── iebc_wards_2022.shx
│   ├── iebc_wards_2022.dbf
│   └── iebc_wards_2022.prj
└── knbs_admin_2019.zip
```
