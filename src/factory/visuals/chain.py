"""Visual provider chain: pixabay -> wikimedia_commons -> pollinations (procedural is the caller's last resort)."""
from __future__ import annotations
from pathlib import Path
from .providers.base import Asset
from .providers.pixabay import PixabayProvider
from .providers.wikimedia import WikimediaProvider
from .providers.pollinations import PollinationsProvider
from ..config import load_config
from ..logging_setup import setup_logging

log = setup_logging("visuals")
PROVIDERS = {"pixabay": PixabayProvider, "wikimedia_commons": WikimediaProvider, "pollinations": PollinationsProvider}


def get_chain() -> list:
    names = load_config().get("visuals", {}).get("providers", list(PROVIDERS))
    return [PROVIDERS[n]() for n in names if n in PROVIDERS]


def fetch_asset(keywords: list[str], orientation: str, kind: str, dest: Path, seed: int = 0,
                exclude_ids: set | None = None) -> Asset | None:
    """Try each provider in order. Failures are logged and skipped; returns None if all fail.

    `exclude_ids` is checked BEFORE download so we never spend a request on an asset we
    already used in this reel.
    """
    excluded = exclude_ids or set()
    for prov in get_chain():
        try:
            if not prov.available():
                continue
            assets = prov.search(keywords, orientation, kind, seed=seed) if prov.name == "pollinations" \
                else prov.search(keywords, orientation, kind)
        except Exception as e:
            log.warning("%s search failed: %s", prov.name, e)
            continue
        for a in assets[:10]:
            if a.asset_id in excluded:
                continue
            try:
                if prov.download(a, dest):
                    return a
            except Exception as e:
                log.warning("%s download failed: %s", prov.name, e)
    return None
