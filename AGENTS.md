# CitySim — Agent Guide

Cities through time, 2357 BCE → 2025, on real data. Main product: `dist/city_pillars.html`, a single-file WebGL2 globe with city pillars (height = √population, thickness = city area), political and religion base layers, an "area in view" info card, model routes and Roman roads. Personal-db item: "City Sim" (id 245).

## Layout

```
city-sim/
├── src/                     # build scripts + page templates (see Build chain)
├── scripts/fetch_zenodo.sh  # resumable Zenodo download
├── figures/                 # static figures (xian_eras.png, palette_preview.png)
├── data -> HDD              # symlink to "Backup Plus1/projects/city-sim-data" (raw/, processed/) — never committed
└── dist/                    # built pages (gitignored): city_pillars (main), city_globe, city_world, city_atlas
```

## Build chain (run from the repo root, `uv run python src/<script>.py`)

| Step | Script | Output |
|------|--------|--------|
| religion lookup (rate-limited, needs retry) | `fetch_religion.py` | `data/raw/wikidata/religion.json` |
| polity rasters, colours, religion | `build_political.py` | `data/processed/political.json` |
| Roman roads | `build_roads.py` | `data/processed/roads.json` |
| cities, land mask, pop grid | `build_pillars.py` (needs the two above) | `data/processed/pillars.json` |
| other page data | `build_world.py`, `build_views.py` | `world.json`, `globe.json`, `city_views.json` |
| inline data into pages | `build_atlas.py` | `dist/*.html` |

Deep links for checking a state: `city_pillars.html#<jump 0-4 or w>_<year>[_<tilt>][_r|n|x|d|b]` (r religion, n religion without inferred, x plain, d roman roads, b model routes + roads).

## Data (all open; HDD holds the raw files)

- Stadestér 1.0, Zenodo 17180328 (cities, 5' population rasters). Use the **non-metro-adjusted** JSON; the metro-adjusted one subtracts suburbs from city cores.
- Natural Earth 50 m land; Cliopatria v0.2.1 polities (CC BY 4.0); Wikidata P140 religion; Itiner-e roads (Zenodo 17122148, CC BY 4.0, EPSG:3395).
- HYDE (Utrecht) is behind an anti-bot wall and NASA SEDAC needs a login: don't script around them.

## Conventions and gotchas

- Raster PNGs hold 4 big-endian bytes = one uint32 population per pixel (RGBA), not an image.
- Pages must fit the window with no page scroll (pillars page does; the older ones don't yet).
- Theme: its own teal/amber "survey" look, not the purple UI theme. Heat ramp is cool→warm.
- Religion layer shows the religion, not the polity; inheritance is strict (IoU ≥ 0.4, ≤ 3 hops, ≤ 2 families) and drawn faded; 2 religions = stripes, 3+ = tiles.
- Local files only: do not publish these pages as claude.ai artifacts unless asked.
