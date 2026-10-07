"""Inline data into the page templates -> dist/*.html.

  city_atlas.html  four city windows at 5' resolution   (data/processed/city_views.json, placeholder "[]")
  city_world.html  whole world at quarter resolution     (data/processed/world.json,      placeholder "{}")

Usage: uv run python src/build_atlas.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    ("atlas.template.html", "city_views.json", "/*__DATA__*/[]", "city_atlas.html"),
    ("world.template.html", "world.json", "/*__DATA__*/{}", "city_world.html"),
]
out_dir = ROOT / "dist"
out_dir.mkdir(exist_ok=True)
for tpl, data, marker, out in PAGES:
    src = ROOT / "data/processed" / data
    if not src.exists():
        print("skip", out, "(missing", data + ")")
        continue
    html = (ROOT / "src" / tpl).read_text().replace(marker, src.read_text().replace("</", "<\\/"))
    (out_dir / out).write_text(html)
    print("wrote", out_dir / out, f"{(out_dir / out).stat().st_size/1e6:.1f} MB")
