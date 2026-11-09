"""Pollinations provider (no key). seed varies per shot."""
from __future__ import annotations
from pathlib import Path
from typing import List
from .base import Asset
from ...visuals import pollinations_url, download


class PollinationsProvider:
    name = "pollinations"

    def available(self) -> bool:
        return True

    def search(self, keywords: list[str], orientation: str = "vertical", kind: str = "image", seed: int = 42) -> List[Asset]:
        if kind != "image":
            return []
        url = pollinations_url(", ".join(keywords), seed=seed)
        return [Asset(provider="pollinations", asset_id=f"pollinations-{seed}", url=url,
                      source_page=url, uploader="pollinations", license="Pollinations", kind="image")]

    def download(self, asset: Asset, dest: Path) -> bool:
        return download(asset.url, dest)
