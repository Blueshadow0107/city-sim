# city-sim

Cities through time: population heatmaps + city size curves from 2357 BCE to 2025, built from real data. A prediction model comes later.

## Data (not in git)
`data/` is a symlink to the HDD (`Backup Plus1/projects/city-sim-data`).
Source: Stadestér 1.0 (Zenodo 17180328, MIT) — population rasters + non-metro-adjusted city JSON.
Fetch with `scripts/fetch_zenodo.sh 17180328 <file> <dest>` (resumable).

## Build
```
uv run python src/build_views.py   # crops rasters + city series -> data/processed/city_views.json
uv run python src/build_atlas.py   # inlines it -> dist/city_atlas.html (open in any browser)
uv run python src/crop_xian.py     # static era figure -> figures/xian_eras.png
```
Deep link for checking a state: `dist/city_atlas.html#<view 0-3>_<year>`, e.g. `#3_1520`.

## Notes
- Rasters are 4320x2160 RGBA PNGs: the 4 bytes (big-endian) are one uint32 population per 5' cell.
- Use the non-metro-adjusted JSON; the metro-adjusted one subtracts suburbs from the core city.
