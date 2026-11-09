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
# Register autostart (Windows)
if sys.platform == "win32":
    try:
        from src.factory.osx.windows import task_xml
        import shutil
        pythonw = shutil.which("pythonw") or sys.executable.replace("python.exe", "pythonw.exe")
        xml = task_xml(pythonw, str(ROOT), str(ROOT))
        xml_path = ROOT / "data" / "task.xml"
        xml_path.write_text(xml, encoding="utf-8")
        subprocess.run(["schtasks", "/Create", "/TN", "ChalisaFactory", "/XML", str(xml_path), "/F"], check=True)
        print("Autostart task registered.")
    except Exception as e:
        print("autostart skip:", e)
print("Done. Run scripts/doctor.py")