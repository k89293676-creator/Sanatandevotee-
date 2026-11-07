"""Uninstall autostart (best effort)."""
from __future__ import annotations
import sys, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
print("Removing scheduled task (Windows)...")
try:
    subprocess.run(["schtasks","/Delete","/TN","ChalisaFactory","/F"], check=False)
except Exception as e:
    print(e)
print("Done.")