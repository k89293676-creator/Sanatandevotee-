"""Pollinations provider (no key)."""
from __future__ import annotations
import urllib.parse
from pathlib import Path
from typing import List
from .base import Asset
from ...visuals import pollinations_url


class PollinationsProvider:
    name = "pollinations"

    def available(self) -> bool:
        return True

    def search(self, keywords: list[str], orientation: str = "vertical", kind: str = "image") -> List[Asset]:
        if kind != "image":
            return []
        prompt = ", ".join(keywords)
        url = pollinations_url(prompt, seed=42)
        return [Asset(provider="pollinations", asset_id="pollinations", url=url,
                     source_page=url, uploader="pollinations", license="Pollinations", kind="image")]

    def download(self, asset: Asset, dest: Path) -> bool:
        import httpx
        try:
            with httpx.stream("GET", asset.url, timeout=120, follow_redirects=True) as r:
                if r.status_code != 200:
                    return False
                with dest.open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            return dest.exists() and dest.stat().st_size > 0
        except Exception:
            return False