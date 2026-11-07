import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.visuals.chain import fetch_asset

def test_chain_runs():
    dest = ROOT / "media" / "cache" / "test_asset.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    a = fetch_asset(["mountain"], "portrait", "image", dest)
    # may be None if network blocked; but should not crash
    assert a is None or dest.exists()