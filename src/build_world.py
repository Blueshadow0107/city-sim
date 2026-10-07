"""Build the world-map data bundle: quarter-resolution population rasters + all cities >= MIN_POP.

Rasters are 4320x2160 (5 arcmin); 4x4 blocks are summed to 1080x540 (20 arcmin, ~37 km at the equator),
so regional totals are preserved. Values are log10-quantized to uint8 and deflated.

Output: data/processed/world.json   (uv run python src/build_world.py)
"""
import base64
import json
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RASTERS = ROOT / "data/raw/stadester/stadester_population_rasters"
JSON_DIR = ROOT / "data/raw/stadester/json_nonmetro"  # whole agglomerations
OUT = ROOT / "data/processed/world.json"
GLOBE_OUT = ROOT / "data/processed/globe.json"

BLOCK = 4
LOG_MAX = 7.5  # log10(people per 20' cell) mapped to 255
MIN_POP = 100_000
FRAMES = [-3000, -2000, -1000] + list(range(0, 1701, 100)) + list(range(1710, 2001, 10)) + [2025]

# name of the historic entry in stadester.json -> nearest GHSL key prefix for the satellite-era series
FOCUS = {
    "Xi'an-China": "ghsl-Xi'an",
    "Qâhirah, Al- (agglomeration)-Egypt": "ghsl-Cairo",
    "Baghdád-Iraq": "ghsl-Baghdad",
    "Ciudad de México-Mexico": "ghsl-Mexico City",
}
BOOKMARKS = [
    {"id": "xian", "title": "Xi'an", "lat": 34.27, "lon": 108.95, "zoom": 14, "cities": ["Xi'an-China"]},
    {"id": "cairo", "title": "Memphis → Cairo", "lat": 30.04, "lon": 31.24, "zoom": 14,
     "cities": ["Badrashayn, Al--Egypt", "Qâhirah, Al- (agglomeration)-Egypt"]},
    {"id": "mesopotamia", "title": "Ur → Baghdad", "lat": 31.8, "lon": 45.0, "zoom": 14,
     "cities": ["Ur-Iraq", "Uruk-Iraq", "Seleucia-Iraq", "Ctesiphon-Iraq", "Baghdád-Iraq"]},
    {"id": "mexico", "title": "Tenochtitlan → Mexico City", "lat": 19.43, "lon": -99.13, "zoom": 14,
     "cities": ["Teotihuacán-Mexico", "Ciudad de México-Mexico"]},
]


def load_pop(year: int) -> np.ndarray:
    rgba = np.ascontiguousarray(np.asarray(Image.open(RASTERS / f"stadester_population_{year}.png").convert("RGBA")))
    return rgba.view(">u4")[..., 0].astype(np.float64)


def series(entry: dict) -> list[int]:
    """Flat [year, pop, year, pop, ...]."""
    pop = entry.get("population") or {}
    out: list[int] = []
    for y, p in sorted(pop.items(), key=lambda kv: int(kv[0])):
        out += [int(y), round(float(p))]
    return out


def main() -> None:
    frames = []
    for y in FRAMES:
        a = load_pop(y)
        h, w = a.shape
        frames.append(a.reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK).sum(axis=(1, 3)))
    stack = np.log10(np.stack(frames) + 1)
    q = np.clip(np.round(stack / LOG_MAX * 255), 0, 255).astype(np.uint8)
    packed = base64.b64encode(zlib.compress(q.tobytes(), 9)).decode()
    print(f"raster {q.shape}  raw={q.nbytes/1e6:.1f} MB  packed={len(packed)/1e6:.1f} MB  max log={stack.max():.2f}")

    hist = json.load(open(JSON_DIR / "stadester.json"))
    ghsl = json.load(open(JSON_DIR / "stadester_ghsl.json"))
    cities, index = [], {}
    keep = set(FOCUS) | {k for b in BOOKMARKS for k in b["cities"]}
    for key, e in hist.items():
        pts = series(e)
        if not pts or not e.get("coords"):
            continue
        if key not in keep and max(pts[1::2]) < MIN_POP:
            continue
        index[key] = len(cities)
        cities.append({"name": e["name"], "country": e.get("country", ""), "lat": round(e["coords"][0], 3),
                       "lon": round(e["coords"][1], 3), "pts": pts})
    for key, prefix in FOCUS.items():
        c = cities[index[key]]
        best = None
        for gk, g in ghsl.items():
            if gk.startswith(prefix) and g.get("coords"):
                d = abs(g["coords"][0] - c["lat"]) + abs(g["coords"][1] - c["lon"])
                if d < 4 and (best is None or d < best[0]):
                    best = (d, g)
        if best:
            c["sat"] = series(best[1])
    bookmarks = [{**b, "cities": [index[k] for k in b["cities"]]} for b in BOOKMARKS]
    print(f"cities >= {MIN_POP:,}: {len(cities)}")

    doc = {"w": q.shape[2], "h": q.shape[1], "frames": FRAMES, "logMax": LOG_MAX, "data": packed,
           "cities": cities, "bookmarks": bookmarks}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote", OUT, f"{OUT.stat().st_size/1e6:.1f} MB")

    # Globe bundle: one deflated chunk per frame (decoded lazily in the page) + a land mask chunk.
    b64z = lambda a: base64.b64encode(zlib.compress(a.tobytes(), 9)).decode()  # noqa: E731
    globe = {
        "w": doc["w"], "h": doc["h"], "frames": FRAMES, "logMax": LOG_MAX,
        "chunks": [b64z(q[i]) for i in range(len(FRAMES))],
        "land": b64z((q > 0).any(axis=0).astype(np.uint8)),
        "cities": cities,
        "bookmarks": [{**b, "zoom": 20} for b in bookmarks],
    }
    GLOBE_OUT.write_text(json.dumps(globe, ensure_ascii=False, separators=(",", ":")))
    print("wrote", GLOBE_OUT, f"{GLOBE_OUT.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
