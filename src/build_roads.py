"""Pack the Itiner-e Roman road network for the globe page.

Source: Itiner-e (de Soto et al., CC BY 4.0), EPSG:3395 (World Mercator, metres, with elevation).
Steps: metres -> lon/lat, Douglas-Peucker simplification (about 1 km), quantize to 1e-3 degree, delta-encode, deflate.

Binary layout (Int32, little endian), repeated per line:  n, meta, start, end, x0, y0, dx1, dy1, ...
  meta  = type (0 main, 1 secondary) + 2 * certainty (0 certain, 1 conjectured, 2 hypothetical)
  start/end = first/last year the road is shown (undated roads get the network window)
Output: data/processed/roads.json   (uv run python src/build_roads.py)
"""
import base64
import json
import math
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/raw/itinere/itinere_roads.geojson"
OUT = ROOT / "data/processed/roads.json"

A = 6378137.0
E = 0.0818191908426
TOL_DEG = 0.009  # about 1 km
WINDOW = (-300, 500)  # most roads are undated; the dataset describes the empire roughly 300 BCE - 300 CE
CERT = {"Certain": 0, "Conjectured": 1, "Hypothetical": 2}


def to_lonlat(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lon = np.degrees(x / A)
    t = np.exp(-y / A)
    phi = np.pi / 2 - 2 * np.arctan(t)
    for _ in range(6):
        s = E * np.sin(phi)
        phi = np.pi / 2 - 2 * np.arctan(t * ((1 - s) / (1 + s)) ** (E / 2))
    return lon, np.degrees(phi)


def simplify(pts: np.ndarray, tol: float) -> np.ndarray:
    """Douglas-Peucker on an (n, 2) array in degrees (x scaled by cos(lat) so tolerance is roughly isotropic)."""
    n = len(pts)
    if n <= 2:
        return pts
    p = pts * np.array([math.cos(math.radians(pts[:, 1].mean())), 1.0])
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = p[i], p[j]
        seg = b - a
        L = math.hypot(*seg)
        v = p[i + 1:j] - a
        d = np.abs(seg[0] * v[:, 1] - seg[1] * v[:, 0]) / L if L > 0 else np.hypot(v[:, 0], v[:, 1])
        k = int(np.argmax(d))
        if d[k] > tol:
            m = i + 1 + k
            keep[m] = True
            stack += [(i, m), (m, j)]
    return pts[keep]


def main() -> None:
    gj = json.load(open(SRC))
    out: list[int] = []
    n_lines = n_vert = n_in = 0
    for f in gj["features"]:
        pr = f["properties"]
        meta = (0 if pr["Route_Type"] == 2 else 1) + 2 * CERT.get(pr.get("Segment_s"), 1)
        lo, up = pr.get("Lower_Date"), pr.get("Upper_Date")
        start = int(lo) if lo is not None and lo != 9999 else WINDOW[0]
        end = int(up) if up is not None and up != 9999 else WINDOW[1]
        for line in f["geometry"]["coordinates"]:
            a = np.asarray(line, dtype=float)
            n_in += len(a)
            lon, lat = to_lonlat(a[:, 0], a[:, 1])
            s = simplify(np.column_stack([lon, lat]), TOL_DEG)
            q = np.round(s * 1000).astype(np.int64)
            d = np.diff(q, axis=0)
            out += [len(q), meta, start, end, int(q[0, 0]), int(q[0, 1])] + d.ravel().tolist()
            n_lines += 1
            n_vert += len(q)
    arr = np.asarray(out, dtype="<i4")
    blob = base64.b64encode(zlib.compress(arr.tobytes(), 9)).decode()
    OUT.write_text(json.dumps({"roads": blob, "lines": n_lines, "vertices": n_vert}))
    print(f"{n_lines} lines, {n_in} -> {n_vert} vertices; wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
