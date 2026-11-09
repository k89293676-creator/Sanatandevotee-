"""Perceptual hashing for visual dedupe.

Difference hash (dHash): resize to 9x8 grayscale, compare each pixel with its
right neighbour. 64 comparisons -> 64 bits. It is cheap, dependency-free (no
scipy/DCT) and catches "same stock photo, different crop" duplicates that an
asset-id check misses.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

SIZE = (9, 8)
THRESHOLD = 6   # out of 64 bits; two near-identical photos typically differ by 0-4


def dhash(image) -> int:
    """Return the 64-bit difference hash of a path or an opened PIL image."""
    im = image if hasattr(image, "convert") else Image.open(Path(image))
    px = im.convert("L").resize(SIZE, Image.LANCZOS).tobytes()   # 9*8 bytes, row-major
    bits = 0
    for y in range(SIZE[1]):
        row = y * SIZE[0]
        for x in range(SIZE[0] - 1):
            bits = (bits << 1) | (1 if px[row + x] > px[row + x + 1] else 0)
    return bits


def distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def is_duplicate(h: int, seen: list[int], threshold: int = THRESHOLD) -> bool:
    return any(distance(h, other) <= threshold for other in seen)
