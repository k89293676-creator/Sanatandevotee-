import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def test_config():
    from src.factory.config import load_config
    c = load_config()
    assert c["posting"]["reels_per_day"] == 2

def test_db_init():
    from src.factory.db import init_db, connect
    init_db()
    conn = connect()
    assert conn.execute("SELECT 1").fetchone()[0] == 1
    conn.close()

def test_captions():
    from src.factory.captions import proportional_timings, build_ass
    t = proportional_timings("a b c d e f", 10.0, max_words=2)
    assert len(t) == 3
    ass = build_ass(t)
    assert "Dialogue" in ass

def test_optimizer():
    from src.factory import optimizer
    optimizer.ensure_arms()
    w = optimizer.weights()
    assert isinstance(w, dict)

def test_verses_count():
    import json
    p = ROOT / "data/packs/shiv_chalisa/verses.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert len(data) == 42

def test_secret_scan_clean():
    import subprocess
    r = subprocess.run(["python", "scripts/secret_scan.py"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr