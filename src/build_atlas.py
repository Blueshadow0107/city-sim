"""Inline data/processed/city_views.json into the atlas template -> dist/city_atlas.html.

Usage: uv run python src/build_atlas.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tpl = (ROOT / "src/atlas.template.html").read_text()
data = (ROOT / "data/processed/city_views.json").read_text().replace("</", "<\\/")
out = ROOT / "dist/city_atlas.html"
out.parent.mkdir(exist_ok=True)
out.write_text(tpl.replace("/*__DATA__*/[]", data))
print("wrote", out, f"{out.stat().st_size/1e6:.1f} MB")
