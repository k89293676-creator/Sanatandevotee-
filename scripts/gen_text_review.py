"""Write the source verse text to docs/TEXT_SOURCE.md for reading/copying.

This is a listing only; it makes no verification claim. `scripts/verify_text.py`
owns docs/TEXT_REVIEW.md and the H1 evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data" / "packs" / "shiv_chalisa" / "verses.json"
OUT = ROOT / "docs" / "TEXT_SOURCE.md"


def main() -> int:
    verses = json.loads(PACK.read_text(encoding="utf-8"))
    lines = ["# Shiv Chalisa verse text (source listing)", "",
             "This file is a plain listing, not a verification report.", ""]
    for v in verses:
        lines.append(f"## {v['seq']}. ({v['kind']})")
        lines.append(v["devanagari"])
        lines.append(f"*{v['roman']}*")
        lines.append(f"Hindi: {v['meaning_hi']}")
        lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("written", OUT.relative_to(ROOT), "units:", len(verses))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
