"""Side-by-side preview of candidate heat ramps on Eurasia at 800 CE (quarter-res cells).

Usage: uv run python src/palette_preview.py   -> figures/palette_preview.png
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
YEAR = 800
LOG_LO, LOG_HI = 1.4, 7.0  # same stretch the pages use: (v - 1.4) / 5.6

RAMPS = {
    "A. Current: wheat → amber → brick → wine": ["#efe3b8", "#e8c374", "#e09a3e", "#c9652b", "#9c2b2f", "#4a0f2a"],
    "B. Ember: deep teal → olive → gold → orange → white-hot": ["#16393b", "#2a6f68", "#8bab4f", "#e3c24a", "#ff9a4d", "#fff1d6"],
    "C. Cool to warm: ice blue → teal → gold → red": ["#dbeaf0", "#8fc4cf", "#3f9a96", "#e0b83a", "#d6542b", "#7a1a2b"],
    "D. Cividis-like (colour-blind safe): navy → olive → yellow": ["#d9e4ec", "#8aa6b8", "#5f7e8e", "#8a8a5c", "#c2b04c", "#f2e24a"],
}


def main() -> None:
    rgba = np.ascontiguousarray(np.asarray(Image.open(ROOT / f"data/raw/stadester/stadester_population_rasters/stadester_population_{YEAR}.png").convert("RGBA")))
    pop = rgba.view(">u4")[..., 0].astype(np.float64)
    h, w = pop.shape
    q = pop.reshape(h // 4, 4, w // 4, 4).sum(axis=(1, 3))
    v = np.log10(q + 1)
    # Eurasia window: lon -15..150, lat 65..-10 on a 1080x540 grid (3 cells per degree)
    x0, x1 = int((-15 + 180) * 3), int((150 + 180) * 3)
    y0, y1 = int((90 - 65) * 3), int((90 + 10) * 3)
    v = v[y0:y1, x0:x1]
    land = (v > 0)[..., None]
    fig, axes = plt.subplots(2, 2, figsize=(14, 7.6), facecolor="#e6ece7")
    for ax, (name, hexes) in zip(axes.flat, RAMPS.items()):
        cmap = LinearSegmentedColormap.from_list(name, hexes)
        t = np.clip((v - LOG_LO) / (LOG_HI - LOG_LO), 0, 1)
        a = np.clip((v - 1.2) / 1.0, 0, 1)[..., None]
        base = np.where(land, np.array([0.933, 0.945, 0.91]), np.array([0.765, 0.835, 0.84]))
        img = cmap(t)[..., :3] * a + base * (1 - a)
        ax.imshow(img, interpolation="nearest")
        ax.set_title(name, fontsize=11, color="#14262a", loc="left")
        ax.axis("off")
    fig.tight_layout()
    out = ROOT / "figures/palette_preview.png"
    fig.savefig(out, dpi=110, facecolor=fig.get_facecolor())
    print("wrote", out)


if __name__ == "__main__":
    main()
