"""Manual sync trigger."""
from __future__ import annotations
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory import sync
url = os.environ.get("RELAY_URL", "http://localhost:8787")
print(sync.get_state(url))