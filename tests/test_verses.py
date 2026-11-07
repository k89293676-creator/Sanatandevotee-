import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.verses import load_pack, upsert_verses, verse_count

def test_load_pack():
    vs = load_pack("shiv_chalisa")
    assert len(vs) == 42

def test_upsert():
    vs = load_pack("shiv_chalisa")
    n = upsert_verses("shiv_chalisa", vs)
    assert n == 42