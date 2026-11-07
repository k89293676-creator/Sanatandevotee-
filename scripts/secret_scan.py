"""Secret scan: regex + gitleaks over working tree and git history."""
from __future__ import annotations
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    (re.compile(r"EAAG[0-9A-Za-z]{20,}"), "Meta token"),
    (re.compile(r"\d{8,10}:[A-Za-z0-9_-]{30,}"), "Telegram bot token"),
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "Google API key"),
    (re.compile(r"sbp_[A-Za-z0-9]{30,}"), "Supabase key"),
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "JWT"),
    (re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"), "generic secret assignment"),
]

SKIP_EXT = {".png", ".jpg", ".jpeg", ".mp3", ".mp4", ".wav", ".pdf", ".ttf", ".woff", ".woff2", ".pyc"}
SKIP_DIRS = {".git", "node_modules", ".wrangler", "media", "logs"}

def scan_tree() -> list:
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in SKIP_EXT:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat, name in PATTERNS:
            for m in pat.finditer(text):
                hits.append((str(p.relative_to(ROOT)), name, m.group(0)[:12] + "..."))
    return hits

def main() -> int:
    hits = scan_tree()
    # gitleaks if available
    try:
        import shutil
        if shutil.which("gitleaks"):
            r = subprocess.run(["gitleaks", "detect", "--source", str(ROOT), "--no-git", "--redact"],
                                capture_output=True, text=True)
            if r.returncode != 0:
                print("gitleaks found issues")
                print(r.stdout[-1000:])
                return 1
    except Exception as e:
        print("gitleaks skip:", e)
    if hits:
        print("SECRET SCAN FAILED:")
        for h in hits:
            print("  ", h)
        return 1
    print("secret scan clean")
    return 0

if __name__ == "__main__":
    sys.exit(main())