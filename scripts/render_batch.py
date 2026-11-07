"""Render batch of planned reels (simplified)."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
print("render_batch: implement per-reel render via factory.render; see daemon.")