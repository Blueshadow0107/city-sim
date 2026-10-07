"""Build the per-view data bundle for the atlas page.

For each view: a window of the Stadestér population rasters (log-quantized uint8, deflated),
nearby cities with their population observations, and the focus-city series.

Output: data/processed/city_views.json   (uv run python src/build_views.py)
"""
import base64
import json
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RASTERS = ROOT / "data/raw/stadester/stadester_population_rasters"
JSON_DIR = ROOT / "data/raw/stadester/json_nonmetro"  # whole agglomerations; the metro-adjusted table carves suburbs out of the core
OUT = ROOT / "data/processed/city_views.json"

PX_PER_DEG = 4320 / 360
HALF_DEG = 6.0
LOG_MAX = 6.5  # log10(people per 5' pixel) mapped to 255
MIN_MARKER_POP = 100_000

# Ten-year steps after 1700, otherwise every available snapshot from 3000 BCE.
FRAMES = [-3000, -2000, -1000] + list(range(0, 1701, 100)) + list(range(1710, 2001, 10)) + [2025]

VIEWS = [
    {"id": "xian", "title": "Xi'an", "subtitle": "Chang'an, capital of the Han and Tang",
     "lat": 34.27, "lon": 108.95, "focus": ["Xi'an-China"], "ghsl": "Xi'an"},
    {"id": "cairo", "title": "Memphis → Cairo", "subtitle": "Nile valley, the longest record here",
     "lat": 30.04, "lon": 31.24,
     "focus": ["Badrashayn, Al--Egypt", "Qâhirah, Al- (agglomeration)-Egypt"], "ghsl": "Cairo"},
    {"id": "mesopotamia", "title": "Ur → Baghdad", "subtitle": "Mesopotamia, where the centre keeps moving",
     "lat": 31.8, "lon": 45.0,
     "focus": ["Ur-Iraq", "Uruk-Iraq", "Seleucia-Iraq", "Ctesiphon-Iraq", "Baghdád-Iraq"], "ghsl": "Baghdad"},
    {"id": "mexico", "title": "Tenochtitlan → Mexico City", "subtitle": "A late start, then a very steep climb",
     "lat": 19.43, "lon": -99.13, "focus": ["Teotihuacán-Mexico", "Ciudad de México-Mexico"], "ghsl": "Mexico City"},
]


def load_pop(year: int) -> np.ndarray:
    rgba = np.ascontiguousarray(np.asarray(Image.open(RASTERS / f"stadester_population_{year}.png").convert("RGBA")))
    return rgba.view(">u4")[..., 0].astype(np.float64)


def bbox(lat: float, lon: float) -> tuple[int, int, int, int]:
    cx = (lon + 180) * PX_PER_DEG
    cy = (90 - lat) * PX_PER_DEG
    r = HALF_DEG * PX_PER_DEG
    return int(cy - r), int(cy + r), int(cx - r), int(cx + r)


def series(entry: dict) -> list[list[float]]:
    pop = entry.get("population") or {}
    return [[int(y), round(float(p))] for y, p in sorted(pop.items(), key=lambda kv: int(kv[0]))]


def main() -> None:
    hist = json.load(open(JSON_DIR / "stadester.json"))
    ghsl = json.load(open(JSON_DIR / "stadester_ghsl.json"))
    rasters = {y: load_pop(y) for y in FRAMES}
    views = []
    for v in VIEWS:
        y0, y1, x0, x1 = bbox(v["lat"], v["lon"])
        h, w = y1 - y0, x1 - x0
        stack = np.stack([np.log10(rasters[y][y0:y1, x0:x1] + 1) for y in FRAMES])
        q = np.clip(np.round(stack / LOG_MAX * 255), 0, 255).astype(np.uint8)
        packed = base64.b64encode(zlib.compress(q.tobytes(), 9)).decode()

        lat_lo, lat_hi = v["lat"] - HALF_DEG, v["lat"] + HALF_DEG
        lon_lo, lon_hi = v["lon"] - HALF_DEG, v["lon"] + HALF_DEG
        cities = []
        for key, e in hist.items():
            pts = series(e)
            if not pts or not e.get("coords"):
                continue
            la, lo = e["coords"]
            if lat_lo <= la <= lat_hi and lon_lo <= lo <= lon_hi and max(p for _, p in pts) >= MIN_MARKER_POP:
                cities.append({"name": e["name"], "lat": la, "lon": lo, "pts": pts, "focus": key in v["focus"]})
        for key in v["focus"]:
            if not any(c["focus"] and hist[key]["name"] == c["name"] for c in cities):
                e = hist[key]
                la, lo = e["coords"]
                cities.append({"name": e["name"], "lat": la, "lon": lo, "pts": series(e), "focus": True})

        # Focus cities last, in the order given in VIEWS (oldest -> newest), so colours and the satellite line line up.
        order = {hist[k]["name"]: i for i, k in enumerate(v["focus"])}
        cities.sort(key=lambda c: (c["focus"], order.get(c["name"], 0) if c["focus"] else 0))

        # Satellite-era (GHSL) series for the nearest matching urban area.
        best = None
        for key, e in ghsl.items():
            if key.startswith("ghsl-" + v["ghsl"]) and e.get("coords"):
                d = abs(e["coords"][0] - v["lat"]) + abs(e["coords"][1] - v["lon"])
                if d < 4.0 and (best is None or d < best[0]):
                    best = (d, e, key)
        sat = series(best[1]) if best else []
        print("  ghsl match:", best[2] if best else None)

        views.append({
            "id": v["id"], "title": v["title"], "subtitle": v["subtitle"],
            "lat": v["lat"], "lon": v["lon"], "half": HALF_DEG, "w": w, "h": h,
            "frames": FRAMES, "logMax": LOG_MAX, "data": packed,
            "cities": cities, "sat": sat,
        })
        print(f"{v['id']:12} {w}x{h}  frames={len(FRAMES)}  cities={len(cities)}  sat={len(sat)}  packed={len(packed)/1e6:.2f} MB")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(views, ensure_ascii=False, separators=(",", ":")))
    print("wrote", OUT, f"{OUT.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
