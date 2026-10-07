"""Fetch Wikidata 'religion or worldview' (P140) for every Cliopatria polity.

Output: data/raw/wikidata/religion.json  {wikidata_id: [religion labels]}   (uv run python src/fetch_religion.py)
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/raw/cliopatria/unz/cliopatria_polities_only_v021.geojson"
OUT = ROOT / "data/raw/wikidata/religion.json"


def main() -> None:
    gj = json.load(open(SRC))
    qids = sorted({f["properties"]["Wikidata"] for f in gj["features"] if f["properties"].get("Wikidata")})
    print(len(qids), "Wikidata ids")
    rel: dict[str, set[str]] = {}
    for i in range(0, len(qids), 100):
        chunk = qids[i:i + 100]
        q = ("SELECT ?s ?rLabel WHERE { VALUES ?s { %s } ?s wdt:P140 ?r . "
             "SERVICE wikibase:label { bd:serviceParam wikibase:language \"en\". } }") % " ".join("wd:" + x for x in chunk)
        req = urllib.request.Request("https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q),
                                     headers={"User-Agent": "citysim/0.1 (personal research project)"})
        for _ in range(6):
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    for b in json.load(r)["results"]["bindings"]:
                        rel.setdefault(b["s"]["value"].rsplit("/", 1)[1], set()).add(b["rLabel"]["value"])
                break
            except urllib.error.HTTPError as e:
                wait = int(e.headers.get("Retry-After", 30)) if e.code == 429 else 10
                print(f"  chunk {i // 100}: HTTP {e.code}, waiting {wait}s", flush=True)
                time.sleep(wait)
        time.sleep(4)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({k: sorted(v) for k, v in rel.items()}, ensure_ascii=False))
    print(f"{len(rel)} ids with a religion -> {OUT}")


if __name__ == "__main__":
    main()
