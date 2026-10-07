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


NCOL = 16


def hue(c: int) -> float:
    """Hue of palette colour c (golden-ratio spacing, so neighbouring indices are far apart). The page uses the same formula."""
    return (c * 0.381966) % 1.0


def hue_gap(a: int, b: int) -> float:
    d = abs(hue(a) - hue(b))
    return min(d, 1 - d)


def adjacency(a: np.ndarray) -> dict[int, set[int]]:
    """Polities that touch each other in the id raster (4-neighbourhood, wrapping around longitude)."""
    adj: dict[int, set[int]] = {}
    shifts = [(a[:, :-1], a[:, 1:]), (a[:-1, :], a[1:, :]), (a[:, -1:], a[:, :1])]
    for p, q in shifts:
        m = (p != q) & (p != 0) & (q != 0)
        for code in np.unique(p[m].astype(np.int64) * 65536 + q[m]):
            i, j = int(code >> 16), int(code & 65535)
            adj.setdefault(i, set()).add(j)
            adj.setdefault(j, set()).add(i)
    return adj


def assign_colours(a: np.ndarray, prev: np.ndarray | None, prev_col: dict[int, int], memory: dict[int, int], K: int) -> dict[int, int]:
    """Succession colouring: keep a polity's colour, else inherit the colour of the earlier polity it overlaps
    most, else pick a colour far (in hue) from every neighbour. Neighbours never share a colour."""
    cnt = np.bincount(a.ravel(), minlength=K + 1)
    present = [i for i in range(1, K + 1) if cnt[i] > 0]
    adj = adjacency(a)
    overlaps: dict[int, list[tuple[int, int]]] = {}
    if prev is not None:
        both = (a != 0) & (prev != 0)
        codes, counts = np.unique(a[both].astype(np.int64) * 65536 + prev[both], return_counts=True)
        for code, n in zip(codes, counts):
            overlaps.setdefault(int(code >> 16), []).append((int(n), int(code & 65535)))
        for v in overlaps.values():
            v.sort(reverse=True)
    best = {i: (overlaps[i][0][0] if i in overlaps else 0) for i in present}
    order = sorted(present, key=lambda i: (i not in prev_col, -best[i], -cnt[i]))
    out: dict[int, int] = {}
    usage = [0] * NCOL
    for i in order:
        cand = prev_col.get(i)
        if cand is None:
            for _, pid in overlaps.get(i, []):
                if pid in prev_col:
                    cand = prev_col[pid]
                    break
        if cand is None:
            cand = memory.get(i)
        used = {out[n] for n in adj.get(i, ()) if n in out}
        if cand is not None and cand not in used:
            out[i] = cand
        else:
            free = [c for c in range(NCOL) if c not in used] or list(range(NCOL))
            out[i] = max(free, key=lambda c: (min((hue_gap(c, u) for u in used), default=1.0), -usage[c]))
        usage[out[i]] += 1
    return out


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

    K = len(names)
    memory: dict[int, int] = {}  # polity id -> last colour it had, for polities that vanish and come back
    prev_ids: np.ndarray | None = None
    prev_col: dict[int, int] = {}
    chunks, pals, total_raw = [], [], 0
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
        col = assign_colours(a, prev_ids, prev_col, memory, K)
        pal = np.zeros(K + 1, dtype=np.uint8)
        for i, c in col.items():
            pal[i] = c
        pals.append(base64.b64encode(zlib.compress(pal.tobytes(), 9)).decode())
        prev_ids, prev_col = a, col
        memory.update(col)
        planes =np.concatenate([(a >> 8).astype(np.uint8).ravel(), (a & 255).astype(np.uint8).ravel()])
        z = zlib.compress(planes.tobytes(), 9)
        total_raw += planes.nbytes
        chunks.append(base64.b64encode(z).decode())
        print(f"  {y:>5}: {len(active):4d} shapes, {len(z)/1e3:6.0f} kB", flush=True)

    doc = {"w": W, "h": H, "years": YEARS, "chunks": chunks, "pals": pals, "ncol": NCOL,
           "polities": [[n, first[n], last[n], wiki[n]] for n in names]}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote", OUT, f"{OUT.stat().st_size/1e6:.1f} MB for {len(YEARS)} snapshots")


if __name__ == "__main__":
    main()
