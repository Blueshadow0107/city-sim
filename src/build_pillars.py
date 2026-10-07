"""Build the data bundle for the WebGL pillar globe.

  - cities >= 100k (same selection as the flat map) with population AND measured area series (area exists from ~1800)
  - median density (people / km^2) by year, used to model city area before area was recorded
  - land mask at 2160x1080 (2x2 max-pool of the union of all raster snapshots), deflated

Output: data/processed/pillars.json   (uv run python src/build_pillars.py)
"""
import base64
import json
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import build_world as bw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/pillars.json"


def flat(d: dict) -> list:
    out: list = []
    for y, v in sorted((d or {}).items(), key=lambda kv: int(kv[0])):
        if v is not None:
            out += [int(y), round(float(v), 2)]
    return out


def land_mask() -> tuple[str, int, int]:
    """Natural Earth 50m land polygons rasterized at 4320x2160, box-filtered to 2160x1080 (antialiased coast)."""
    gj = json.load(open(ROOT / "data/raw/naturalearth/ne_50m_land.geojson"))
    big_w, big_h = 4320, 2160
    img = Image.new("L", (big_w, big_h), 0)
    draw = ImageDraw.Draw(img)
    xy = lambda ring: [((lo + 180) / 360 * big_w, (90 - la) / 180 * big_h) for lo, la in ring]  # noqa: E731
    for f in gj["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            draw.polygon(xy(poly[0]), fill=255)
            for hole in poly[1:]:
                draw.polygon(xy(hole), fill=0)
    small = img.resize((big_w // 2, big_h // 2), Image.BOX)
    arr = np.asarray(small, dtype=np.uint8)
    return base64.b64encode(zlib.compress(arr.tobytes(), 9)).decode(), arr.shape[1], arr.shape[0]


def main() -> None:
    hist = json.load(open(bw.JSON_DIR / "stadester.json"))
    ghsl = json.load(open(bw.JSON_DIR / "stadester_ghsl.json"))

    # median density by year over every entry that has both population and area
    by_year: dict[int, list[float]] = {}
    for e in hist.values():
        pop, area = e.get("population") or {}, e.get("area") or {}
        for y, a in area.items():
            if a and y in pop and pop[y] >= 20_000:
                by_year.setdefault(int(y), []).append(pop[y] / a)
    dens = [[y, round(float(np.median(v)))] for y, v in sorted(by_year.items()) if len(v) >= 30]
    print("density medians:", dens[:3], "...", dens[-3:], f"({len(dens)} years)")

    keep = set(bw.FOCUS) | {k for b in bw.BOOKMARKS for k in b["cities"]}
    cities, index, n_area = [], {}, 0
    for key, e in hist.items():
        pts = bw.series(e)
        if not pts or not e.get("coords"):
            continue
        if key not in keep and max(pts[1::2]) < bw.MIN_POP:
            continue
        area = flat(e.get("area"))
        n_area += bool(area)
        index[key] = len(cities)
        c = {"name": e["name"], "country": e.get("country", ""), "lat": round(e["coords"][0], 3),
             "lon": round(e["coords"][1], 3), "pts": pts}
        if area:
            c["area"] = area
        cities.append(c)
    print(f"cities: {len(cities)}   with measured area: {n_area}")

    for key, prefix in bw.FOCUS.items():
        c = cities[index[key]]
        best = None
        for gk, g in ghsl.items():
            if gk.startswith(prefix) and g.get("coords"):
                d = abs(g["coords"][0] - c["lat"]) + abs(g["coords"][1] - c["lon"])
                if d < 4 and (best is None or d < best[0]):
                    best = (d, g)
        if best:
            c["sat"] = bw.series(best[1])

    land, lw, lh = land_mask()
    bookmarks = [{**b, "cities": [index[k] for k in b["cities"]], "range": 0.35, "tilt": 55} for b in bw.BOOKMARKS]
    political = json.load(open(ROOT / "data/processed/political.json"))  # run build_political.py first
    doc = {"land": {"w": lw, "h": lh, "data": land}, "dens": dens, "cities": cities, "bookmarks": bookmarks,
           "political": political}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote", OUT, f"{OUT.stat().st_size/1e6:.1f} MB  (land mask {len(land)/1e3:.0f} kB)")


if __name__ == "__main__":
    main()
