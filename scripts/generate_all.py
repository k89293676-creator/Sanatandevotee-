"""Generate all: verses -> scripts -> plan."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.verses import load_pack, upsert_verses
from src.factory import scriptgen, planner
vs = load_pack("shiv_chalisa")
print("upserted", upsert_verses("shiv_chalisa", vs))
print(scriptgen.run("shiv_chalisa"))
print(planner.plan("shiv_chalisa"))