"""Procedural stills (always available, no network): gradient + soft diya glow + bokeh + grain. Different per style/seed."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

PALETTES = {
    "cosmic_blue":    ((8, 12, 40), (40, 30, 110), (120, 170, 255)),
    "ash_monochrome": ((14, 14, 16), (60, 60, 66), (200, 200, 205)),
    "golden_diya":    ((22, 8, 4), (110, 45, 10), (255, 190, 80)),
    "himalaya_dawn":  ((20, 24, 50), (190, 110, 90), (255, 220, 170)),
    "forest_night":   ((4, 16, 12), (14, 70, 50), (150, 255, 190)),
}


def make_still(dest: Path, style: str = "golden_diya", seed: int = 0, w: int = 1350, h: int = 2400) -> Path:
    rng = np.random.default_rng(seed + 1000)
    c0, c1, glow = [np.array(c, dtype=np.float32) for c in PALETTES.get(style, PALETTES["golden_diya"])]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ty = yy / h
    img = c0[None, None] * (1 - ty[..., None]) + c1[None, None] * ty[..., None]
    # soft light source (diya / moon / sun) at a seed-dependent position
    cx, cy = w * rng.uniform(0.3, 0.7), h * rng.uniform(0.45, 0.75)
    d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (w * 0.45) ** 2
    img += glow[None, None] * np.exp(-d2 * 2.2)[..., None] * 0.85
    # flame teardrop
    fl = np.exp(-(((xx - cx) / 38) ** 2 + ((yy - (cy - 30)) / (95 + 30 * (xx > 0))) ** 2))
    img += np.array([255, 235, 170], dtype=np.float32)[None, None] * fl[..., None] * 0.9
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    # bokeh
    bok = Image.new("RGB", (w, h), (0, 0, 0))
    px = bok.load()
    from PIL import ImageDraw
    dr = ImageDraw.Draw(bok)
    for _ in range(26):
        r = int(rng.uniform(25, 90)); x, y = int(rng.uniform(0, w)), int(rng.uniform(0, h))
        col = tuple(int(v * rng.uniform(0.25, 0.6)) for v in glow)
        dr.ellipse([x - r, y - r, x + r, y + r], fill=col)
    bok = bok.filter(ImageFilter.GaussianBlur(18))
    arr = np.asarray(im, dtype=np.float32) + np.asarray(bok, dtype=np.float32) * 0.55
    arr += rng.normal(0, 3.0, arr.shape).astype(np.float32)          # grain
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(dest, quality=92)
    return dest
