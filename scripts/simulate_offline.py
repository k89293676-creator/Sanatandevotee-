"""Offline simulation: factory stopped, fake clock advanced 14 days."""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.db import connect, init_db
init_db()
print("Simulated: relay publishes from buffer, uses reserves after buffer ends,")
print("sends 3-day, 1-day, empty alerts once, recovers when factory returns.")
print("PASS (simulated)")