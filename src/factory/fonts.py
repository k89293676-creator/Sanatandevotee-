"""Font coverage checks. Prevents the 'tofu box' bug (Latin text in a Devanagari-only font)."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from fontTools.ttLib import TTFont

DEVANAGARI = ("Noto Sans Devanagari", "NotoSansDevanagari-Bold.ttf")
LATIN = ("DejaVu Sans", "DejaVuSans-Bold.ttf")
_IGNORED = {"\n", "\r", "\t", " ", "‌", "‍", " "}


@lru_cache(maxsize=8)
def _cmap(path: str) -> frozenset:
    return frozenset(TTFont(path).getBestCmap().keys())


def missing_glyphs(text: str, font_path: Path) -> list[str]:
    cm = _cmap(str(font_path))
    return sorted({ch for ch in text if ch not in _IGNORED and ord(ch) not in cm})


def check_strings(strings: dict[str, str], fonts_dir: Path, font_file: str = DEVANAGARI[1]) -> dict[str, list[str]]:
    """Return {label: [missing chars]} for every on-screen string that the font cannot draw."""
    fp = Path(fonts_dir) / font_file
    bad = {}
    for label, s in strings.items():
        m = missing_glyphs(s, fp)
        if m:
            bad[label] = m
    return bad


def is_latin_text(s: str) -> bool:
    return any(("a" <= c <= "z") or ("A" <= c <= "Z") for c in s)
