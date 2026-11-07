import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.tts import synthesize

def test_tts_cache():
    p1 = synthesize("जय शिव", "hi-IN-MadhurNeural")
    p2 = synthesize("जय शिव", "hi-IN-MadhurNeural")
    assert p1 == p2
    assert p1.exists()