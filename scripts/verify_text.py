"""Verify verse text from two independent sources."""
from __future__ import annotations
import sys, json, difflib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
print("verify_text: fetch two Devanagari sources, diff, report discrepancies to docs/TEXT_REVIEW.md")
print("Sources to fetch: configure URLs in this script")
# Placeholder: user must provide URLs
print("Not yet automated; manual review required (H1 gate)")