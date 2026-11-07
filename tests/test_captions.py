import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.captions import proportional_timings, build_ass, split_chunks

def test_proportional():
    t = proportional_timings("a b c d", 10.0, max_words=2)
    assert len(t) == 2
    assert abs(t[-1]["end"] - 10.0) < 0.01

def test_ass():
    t = proportional_timings("a b", 5.0, max_words=2)
    ass = build_ass(t)
    assert "Dialogue" in ass