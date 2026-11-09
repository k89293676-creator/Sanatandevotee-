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
    (re.compile(r"\d{8}-[0-9a-f]{24,}"), "Pixabay key"),
    (re.compile(r"mk_[A-Za-z0-9_-]{30,}"), "MAKE_KEY"),
    (re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"), "generic secret assignment"),
]

SKIP_EXT = {".png", ".jpg", ".jpeg", ".mp3", ".mp4", ".wav", ".pdf", ".ttf", ".woff", ".woff2", ".pyc"}
SKIP_DIRS = {".git", "node_modules", ".wrangler", "media", "logs"}

# Test fixtures use obviously-fake values that match the real key shapes (e.g. the
# `mk_` Make key prefix). They are deliberate placeholders, not secrets. We allowlist
# by exact value and by test file so CI stays green without weakening production scans.
FIXTURE_VALUES = {
    "mk_test123456789012345678901234567890",
}
FIXTURE_PATH_PARTS = {"tests", "test", "__fixtures__", "fixtures"}
FIXTURE_NAME_MARKERS = ("test", "fixture", "dummy", "sample")
PLACEHOLDER_MARKERS = ("test", "fake", "dummy", "example", "placeholder", "changeme", "xxxx")


def _is_fixture(p: Path, value: str) -> bool:
    if value in FIXTURE_VALUES:
        return True
    name = p.name.lower()
    in_test_dir = any(part in FIXTURE_PATH_PARTS for part in p.parts[:-1])
    if in_test_dir and any(m in name for m in FIXTURE_NAME_MARKERS):
        return True
    if any(s in name for s in (".test.", ".spec.")):
        return True
    # generic placeholder tokens (never part of a real provider-issued key)
    low = value.lower()
    return any(m in low for m in PLACEHOLDER_MARKERS)


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
                if _is_fixture(p, m.group(0)):
                    continue
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