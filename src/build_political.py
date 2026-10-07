"""Rasterize Cliopatria polity borders into per-snapshot id maps for the globe shader.

Each snapshot is a 2160x1080 (half-resolution) uint16 grid of polity ids (0 = no polity), drawn largest-first
so smaller polities sit on top of their overlords. Stored as two byte planes (high, low), deflated.

Output: data/processed/political.json   (uv run python src/build_political.py)
"""
import base64
import json
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/raw/cliopatria/unz/cliopatria_polities_only_v021.geojson"
OUT = ROOT / "data/processed/political.json"

W, H = 2160, 1080
YEARS = list(range(-2400, 1001, 100)) + list(range(1050, 1801, 50)) + list(range(1825, 2001, 25)) + [2024]


def main() -> None:
    gj = json.load(open(SRC))
    feats = [f for f in gj["features"] if f["geometry"]]
    # polity ids ordered by first appearance, so ids are stable and neighbours in time get unrelated hues
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    wiki: dict[str, str] = {}
    for f in feats:
        p = f["properties"]
        n = p["Name"]
        first[n] = min(first.get(n, 10**9), p["FromYear"])
        last[n] = max(last.get(n, -10**9), p["ToYear"])
        wiki.setdefault(n, p.get("Wikipedia") or "")
    names = sorted(first, key=lambda n: (first[n], n))
    pid = {n: i + 1 for i, n in enumerate(names)}
    print(f"{len(feats)} shapes, {len(names)} polities")

    chunks, total_raw = [], 0
    for y in YEARS:
        active = [f for f in feats if f["properties"]["FromYear"] <= y <= f["properties"]["ToYear"]]
        active.sort(key=lambda f: -(f["properties"].get("Area") or 0))
        img = Image.new("I", (W, H), 0)
        draw = ImageDraw.Draw(img)
        for f in active:
            g, v = f["geometry"], pid[f["properties"]["Name"]]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            for poly in polys:
                ring = [((lo + 180) / 360 * W, (90 - la) / 180 * H) for lo, la in poly[0]]
                if len(ring) >= 3:
                    draw.polygon(ring, fill=v)
        a = np.asarray(img, dtype=np.uint32).astype(np.uint16)
        planes = np.concatenate([(a >> 8).astype(np.uint8).ravel(), (a & 255).astype(np.uint8).ravel()])
        z = zlib.compress(planes.tobytes(), 9)
        total_raw += planes.nbytes
        chunks.append(base64.b64encode(z).decode())
        print(f"  {y:>5}: {len(active):4d} shapes, {len(z)/1e3:6.0f} kB", flush=True)

    doc = {"w": W, "h": H, "years": YEARS, "chunks": chunks,
           "polities": [[n, first[n], last[n], wiki[n]] for n in names]}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote", OUT, f"{OUT.stat().st_size/1e6:.1f} MB for {len(YEARS)} snapshots")


if __name__ == "__main__":
    main()
