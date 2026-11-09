"""Run all checks and print real results."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def run(cmd, cwd=ROOT):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()

print("=== pytest ===")
rc, out = run(["python", "-m", "pytest", "-q"])
print(out.splitlines()[-3:] if out else "no output")
print("exit", rc)

print("=== vitest ===")
rc, out = run(["cmd", "/c", "node_modules\\.bin\\vitest.cmd", "run"], cwd=ROOT / "relay")
print(out.splitlines()[-3:] if out else "no output")
print("exit", rc)

print("=== secret_scan ===")
rc, out = run(["python", "scripts/secret_scan.py"])
print(out)
print("exit", rc)

print("=== doctor ===")
rc, out = run(["python", "scripts/doctor.py"])
print(out)
print("exit", rc)