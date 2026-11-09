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