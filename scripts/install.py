"""Idempotent installer."""
from __future__ import annotations
import sys, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
print("Installing deps...")
subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT/"requirements.txt")], check=False)
print("Init db...")
from src.factory.db import init_db
init_db()
print("Register git hooks...")
try:
    subprocess.run(["git","config","core.hooksPath",".githooks"], cwd=ROOT, check=True)
except Exception as e:
    print("git hooks skip:", e)
print("Done. Run scripts/doctor.py")