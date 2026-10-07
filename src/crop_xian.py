"""Crop a window around a city from the Stadester population PNG rasters and plot eras side by side.

Rasters are 4320x2160 equirectangular (5 arcmin/px) RGBA PNGs where the 4 bytes (R,G,B,A = big-endian) are one uint32 population count per pixel.
Usage: uv run python src/crop_xian.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parents[1]
RASTERS = ROOT / "data/raw/stadester/stadester_population_rasters"
OUT = ROOT / "figures"

LAT, LON = 34.27, 108.95  # Xi'an
HALF_DEG = 5.0
YEARS = [-3000, -2000, -1000, 0, 700, 1000, 1500, 1800, 1900, 2000]
PX_PER_DEG = 4320 / 360


def load_pop(year: int) -> np.ndarray:
    rgba = np.ascontiguousarray(np.asarray(Image.open(RASTERS / f"stadester_population_{year}.png").convert("RGBA")))
    return rgba.view(">u4")[..., 0].astype(np.float64)


def window(img: np.ndarray) -> np.ndarray:
    cx = (LON + 180) * PX_PER_DEG
    cy = (90 - LAT) * PX_PER_DEG
    r = HALF_DEG * PX_PER_DEG
    return img[int(cy - r):int(cy + r), int(cx - r):int(cx + r)]


def main() -> None:
    fig, axes = plt.subplots(2, 5, figsize=(16, 7), facecolor="#12081f")
    for ax, year in zip(axes.flat, YEARS):
        pop = window(load_pop(year))
        print(year, "window total pop", f"{pop.sum():,.0f}", "max px", f"{pop.max():,.0f}")
        ax.imshow(np.log10(pop + 1), cmap="magma", vmin=0, vmax=6, interpolation="nearest")
        ax.plot(pop.shape[1] / 2, pop.shape[0] / 2, "c+", ms=10)
        label = f"{-year} BCE" if year < 0 else f"{year} CE"
        ax.set_title(label, color="#d6c2ff")
        ax.axis("off")
    fig.suptitle("Xi'an region (±5°) — Stadestér population raster, brighter = denser (log10 people/pixel)", color="#d6c2ff")
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / "xian_eras.png", dpi=130, facecolor=fig.get_facecolor(), bbox_inches="tight")
    print("wrote", OUT / "xian_eras.png")


if __name__ == "__main__":
    main()
