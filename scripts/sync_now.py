"""Manual sync trigger."""
from __future__ import annotations
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory import sync
import yaml
cfg = yaml.safe_load(open(ROOT / "config" / "config.yaml", encoding="utf-8"))
url = os.environ.get("RELAY_URL", cfg.get("relay", {}).get("url", "http://localhost:8787"))
print(sync.get_state(url))