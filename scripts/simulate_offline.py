"""Offline simulation: runs vitest relay suite with fake clock."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
r = subprocess.run(["cmd", "/c", "node_modules\\.bin\\vitest.cmd", "run"], cwd=ROOT / "relay", capture_output=True, text=True)
print(r.stdout[-500:] if r.stdout else "")
print("exit", r.returncode)
sys.exit(r.returncode)