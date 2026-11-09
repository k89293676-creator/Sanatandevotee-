import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.captions import split_chunks, proportional_timings, build_timings

def test_split_chunks():
    chunks = split_chunks("जय गिरिजा। दिन दयाला।", max_words=5)
    assert len(chunks) >= 1

def test_proportional():
    chunks = split_chunks("a b c d", max_words=2)
    t = proportional_timings(chunks, 10.0)
    assert len(t) == len(chunks)
    assert abs(t[-1]["end"] - 10.0) < 0.5

def test_build_timings():
    t = build_timings("जय शिव", 5.0)
    assert len(t) >= 1


def test_ass_header_is_complete():
    """Regression: a generated .ass once shipped without WrapStyle and with a broken style block."""
    from src.factory.captions import build_ass
    t = proportional_timings(split_chunks("जय शिव शंकर। हर हर महादेव।", max_words=3), 8.0)
    ass = build_ass(t, 8.0, "हुक", "बैज", ["कल मिलेंगे"], {"accent": "&H0040B0FF"})
    assert "WrapStyle: 2" in ass
    assert "ScaledBorderAndShadow: yes" in ass
    assert ass.count("[V4+ Styles]") == 1
    style_lines = [ln for ln in ass.splitlines() if ln.startswith("Style:")]
    assert len(style_lines) >= 5
    # every style line must have the same field count as its Format declaration
    fmt = next(ln for ln in ass.splitlines() if ln.startswith("Format: Name"))
    fields = len(fmt.split(",", 1)[1].split(","))
    assert all(len(ln.split(",", 1)[1].split(",")) == fields for ln in style_lines)
    assert ass.rstrip().endswith(ass.rstrip().splitlines()[-1])