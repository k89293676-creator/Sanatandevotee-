"""Monetisation tracker: milestones, affiliate (gated)."""
from __future__ import annotations
from pathlib import Path
import json
from .config import project_root
from .logging_setup import setup_logging

log = setup_logging("monetisation")
AFF = project_root() / "data" / "affiliate.json"


def affiliate_active() -> bool:
    if not AFF.exists():
        return False
    try:
        d = json.loads(AFF.read_text(encoding="utf-8"))
        return bool(d.get("tag"))
    except Exception:
        return False


def milestone_check(followers: int) -> list:
    milestones = [500, 1000, 5000, 10000]
    return [m for m in milestones if followers >= m]