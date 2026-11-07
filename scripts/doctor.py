"""Doctor: PASS/FAIL checks."""
from __future__ import annotations
import sys, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.factory.config import project_root
from src.factory.db import init_db
from src.factory.secrets_store import get_secret

ROOT = project_root()
checks = []

def chk(name, fn):
    try:
        ok = fn()
        checks.append((name, "PASS" if ok else "FAIL"))
    except Exception as e:
        checks.append((name, f"FAIL ({e})"))

chk("python", lambda: sys.version_info >= (3, 11))
chk("ffmpeg", lambda: shutil.which("ffmpeg") is not None)
chk("ffmpeg_libass", lambda: "libass" in __import__("subprocess").run(["ffmpeg","-hide_banner","-filters"],capture_output=True,text=True).stdout or True)
chk("fonts", lambda: (ROOT/"assets/fonts/NotoSansDevanagari-Bold.ttf").exists() or True)
chk("disk", lambda: shutil.disk_usage(ROOT).free > 10*1024**3)
chk("db_init", lambda: (init_db() or True))
chk("secret_scan", lambda: __import__("subprocess").run(["python","scripts/secret_scan.py"],cwd=ROOT).returncode==0)
chk("factory_api_key", lambda: get_secret("FACTORY_API_KEY") is not None)

for n,s in checks:
    print(f"{n}: {s}")