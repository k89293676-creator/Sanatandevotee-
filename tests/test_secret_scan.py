import sys, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def test_secret_scan_clean():
    r = subprocess.run(["python", "scripts/secret_scan.py"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0