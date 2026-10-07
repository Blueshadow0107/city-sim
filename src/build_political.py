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

# Religion families (index 0 = unknown). The page uses the same order.
FAMILIES = ["Unknown", "Christianity", "Islam", "Hinduism", "Buddhism", "Judaism", "East Asian", "Zoroastrianism",
            "Ancient & indigenous", "Other"]
RULES = [  # (family index, substrings of the lower-cased Wikidata label); first matching rule wins
    (9, ["agnostic", "secular", "irreligion", "atheism", "jain", "sikh"]),
    (6, ["shinbutsu", "taoism", "confuci", "chinese folk", "shinto", "heaven worship", "ryukyuan", "caodai", "hòa hảo", "ancestor"]),
    (4, ["buddh", "theravāda", "mahāyāna"]),
    (3, ["hindu", "shaiv", "vedic"]),
    (2, ["islam", "sunni", "shia", "shiism", "alevi", "bektashi", "sammān", "ahmadiyya"]),
    (1, ["christian", "catholic", "orthodox", "protestant", "luther", "reformed", "church of england", "arian", "nestorian",
         "apostolic", "coptic", "church", "old believers", "gereformeerde", "latin church"]),
    (5, ["judaism", "israelite"]),
    (7, ["zoroast"]),
    (8, ["pagan", "tengri", "shaman", "animis", "african religion", "yoruba", "greek religion", "roman religion", "gallo-roman",
         "ancient egypt", "babylonian", "sumerian", "hittite", "etruscan", "illyrian", "thracian", "scythian", "baltic", "mythology",
         "aztec", "inca", "longhouse", "polytheism", "bon", "kirat", "kejawen", "arabian", "germanic"]),
]


def family_of(label: str) -> int:
    low = label.lower()
    for fam, keys in RULES:
        if any(k in low for k in keys):
            return fam
    return 9


def known_religions(feats) -> dict[str, tuple[int, str]]:
    """polity name -> (family, label text) from Wikidata P140; the family with most labels wins, world religions win ties."""
    rel = json.load(open(ROOT / "data/raw/wikidata/religion.json"))
    q_of = {f["properties"]["Name"]: f["properties"]["Wikidata"] for f in feats if f["properties"].get("Wikidata")}
    out: dict[str, tuple[int, str]] = {}
    for name, q in q_of.items():
        labels = rel.get(q)
        if not labels:
            continue
        votes: dict[int, int] = {}
        for lab in labels:
            votes[family_of(lab)] = votes.get(family_of(lab), 0) + 1
        fam = max(votes, key=lambda k: (votes[k], -k))
        out[name] = (fam, ", ".join(labels[:2]))
    return out


def known_religions(feats) -> dict[str, tuple[int, str]]:
    """polity name -> (family bitmask, label text) from Wikidata P140. Bit (f-1) is set for every family f the polity lists;
    the uninformative 'Other' bucket is dropped when a real religion is also listed."""
    rel = json.load(open(ROOT / "data/raw/wikidata/religion.json"))
    q_of = {f["properties"]["Name"]: f["properties"]["Wikidata"] for f in feats if f["properties"].get("Wikidata")}
    out: dict[str, tuple[int, str]] = {}
    for name, q in q_of.items():
        labels = rel.get(q)
        if not labels:
            continue
        fams = {family_of(lab) for lab in labels}
        if len(fams) > 1:
            fams.discard(9)
        out[name] = (sum(1 << (f - 1) for f in fams), ", ".join(labels[:3]))
    return out


INFERRED = 0x8000  # flag bit in the uint16 stored per polity; bits 0-8 are the family mask, bits 12-14 count successions
MIN_IOU = 0.40     # a predecessor must cover at least 40% of (successor union predecessor) to pass its religion on
MAX_HOPS = 3       # inferred religions are dropped after this many successions


def assign_religion(a: np.ndarray, prev: np.ndarray | None, prev_rel: dict[int, int], known: dict[int, int], K: int) -> dict[int, int]:
    """uint16 per polity: family bitmask, plus INFERRED when it was not recorded. Known polities keep their recorded set.
    Others inherit only across a clearly continuous successor: a predecessor whose territory overlaps theirs with
    overlap/union >= MIN_IOU (so a small successor does not inherit from a vast empire it came out of), at most two
    families (each needs 30% of the polity's area among such predecessors), and at most MAX_HOPS successions."""
    cnt = np.bincount(a.ravel(), minlength=K + 1)
    present = [i for i in range(1, K + 1) if cnt[i] > 0]
    overlaps: dict[int, list[tuple[int, int]]] = {}
    pcnt = np.bincount(prev.ravel(), minlength=K + 1) if prev is not None else None
    if prev is not None:
        both = (a != 0) & (prev != 0)
        codes, counts = np.unique(a[both].astype(np.int64) * 65536 + prev[both], return_counts=True)
        for code, n in zip(codes, counts):
            overlaps.setdefault(int(code >> 16), []).append((int(n), int(code & 65535)))
    out: dict[int, int] = {}
    for i in present:
        if i in known:
            out[i] = known[i]
            continue
        votes: dict[int, int] = {}
        hops = 0
        for n, pid in overlaps.get(i, []):
            iou = n / (cnt[i] + pcnt[pid] - n)
            pv = prev_rel.get(pid, 0)
            if iou < MIN_IOU or not pv & 0x1FF:
                continue
            h = (pv >> 12) & 7
            h = h if pid == i else h + 1  # the same polity carried over a snapshot is not a new succession
            if h > MAX_HOPS:
                continue
            hops = max(hops, h)
            for f in range(9):
                if pv >> f & 1:
                    votes[f] = votes.get(f, 0) + n
        top = sorted((f for f in votes if votes[f] >= 0.30 * cnt[i]), key=lambda f: -votes[f])[:2]
        if top:
            out[i] = sum(1 << f for f in top) | INFERRED | (hops << 12)
    return out


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
    known_by_name = known_religions(feats)
    known = {pid[n]: v[0] for n, v in known_by_name.items()}
    print(f"religion recorded for {len(known)} of {K} polities")
    memory: dict[int, int] = {}  # polity id -> last colour it had, for polities that vanish and come back
    prev_ids: np.ndarray | None = None
    prev_col: dict[int, int] = {}
    prev_rel: dict[int, int] = {}
    chunks, pals, rels, total_raw = [], [], [], 0
    cov_known, cov_all = [], []
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
        rel = assign_religion(a, prev_ids, prev_rel, known, K)
        rel_arr = np.zeros(K + 1, dtype=np.uint16)
        for i, v in rel.items():
            rel_arr[i] = v
        rels.append(base64.b64encode(zlib.compress(rel_arr.tobytes(), 9)).decode())
        wts = np.cos((90 - (np.arange(H) + 0.5) * 180 / H) * np.pi / 180)[:, None] * np.ones((1, W))
        land = a != 0
        cov_known.append((wts * (land & ((rel_arr[a] & 0x1FF) != 0) & ((rel_arr[a] & INFERRED) == 0))).sum() / max((wts * land).sum(), 1e-9))
        cov_all.append((wts * (land & ((rel_arr[a] & 0x1FF) != 0))).sum() / max((wts * land).sum(), 1e-9))
        prev_rel = rel
        prev_ids, prev_col = a, col
        memory.update(col)
        planes =np.concatenate([(a >> 8).astype(np.uint8).ravel(), (a & 255).astype(np.uint8).ravel()])
        z = zlib.compress(planes.tobytes(), 9)
        total_raw += planes.nbytes
        chunks.append(base64.b64encode(z).decode())
        print(f"  {y:>5}: {len(active):4d} shapes, {len(z)/1e3:6.0f} kB", flush=True)

    print(f"religion coverage of polity land, mean over snapshots: recorded {np.mean(cov_known):.0%}, with inheritance {np.mean(cov_all):.0%}")
    for y, k, al in list(zip(YEARS, cov_known, cov_all))[::6]:
        print(f"   {y:>6}: recorded {k:4.0%}  with inheritance {al:4.0%}")
    doc = {"w": W, "h": H, "years": YEARS, "chunks": chunks, "pals": pals, "rels": rels, "ncol": NCOL, "families": FAMILIES,
           "polities": [[n, first[n], last[n], wiki[n], known_by_name.get(n, (0, ""))[1]] for n in names]}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote", OUT, f"{OUT.stat().st_size/1e6:.1f} MB for {len(YEARS)} snapshots")


if __name__ == "__main__":
    main()
