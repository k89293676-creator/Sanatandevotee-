"""Smoke test: imports + config + db."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.config import load_config
from src.factory.db import init_db
cfg = load_config()
init_db()
print("smoke: config loaded, db init ok")
print("reels_per_day:", cfg["posting"]["reels_per_day"])