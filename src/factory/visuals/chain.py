"""Visual provider chain."""
from __future__ import annotations
from pathlib import Path
from typing import List
from .providers.base import Asset
from .providers.pixabay import PixabayProvider
from .providers.wikimedia import WikimediaProvider
from .providers.pollinations import PollinationsProvider
from ..config import load_config

PROVIDERS = {
    "pixabay": PixabayProvider,
    "wikimedia_commons": WikimediaProvider,
    "pollinations": PollinationsProvider,
}


def get_chain() -> list:
    cfg = load_config()
    names = cfg.get("visuals", {}).get("providers", ["pixabay", "wikimedia_commons", "pollinations"])
    chain = []
    for n in names:
        cls = PROVIDERS.get(n)
        if cls:
            chain.append(cls())
    return chain


def fetch_asset(keywords: list[str], orientation: str, kind: str, dest: Path) -> Asset | None:
    for prov in get_chain():
        if not prov.available():
            continue
        try:
            assets = prov.search(keywords, orientation, kind)
        except Exception:
            assets = []
        for a in assets:
            if prov.download(a, dest):
                return a
    return None