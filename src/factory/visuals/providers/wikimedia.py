"""Wikimedia Commons provider (no key), CC0/PD only."""
from __future__ import annotations
import httpx
from typing import List
from pathlib import Path
from .base import Asset
from ...logging_setup import setup_logging

log = setup_logging("wikimedia")


class WikimediaProvider:
    name = "wikimedia"

    def available(self) -> bool:
        return True

    def search(self, keywords: list[str], orientation: str = "vertical", kind: str = "image") -> List[Asset]:
        if kind != "image":
            return []
        q = " ".join(keywords)
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query", "format": "json", "generator": "search",
            "gsrnamespace": "6", "gsrsearch": q, "gsrlimit": "10",
            "prop": "imageinfo", "iiprop": "url|extmetadata",
        }
        assets = []
        try:
            r = httpx.get(url, params=params, timeout=30)
            if r.status_code != 200:
                return []
            pages = r.json().get("query", {}).get("pages", {})
            for pid, p in pages.items():
                info = (p.get("imageinfo") or [{}])[0]
                meta = info.get("extmetadata", {})
                lic = meta.get("LicenseShortName", {}).get("value", "")
                if lic not in ("CC0", "Public domain", "PD", "PDM"):
                    continue
                assets.append(Asset(
                    provider="wikimedia", asset_id=str(pid),
                    url=info.get("url", ""), source_page=info.get("descriptionurl", ""),
                    uploader=meta.get("Artist", {}).get("value", ""),
                    license=lic, kind="image"))
        except Exception as e:
            log.warning("wikimedia err %s", e)
        return assets[:5]

    def download(self, asset: Asset, dest: Path) -> bool:
        import httpx as h
        try:
            with h.stream("GET", asset.url, timeout=120, follow_redirects=True) as r:
                if r.status_code != 200:
                    return False
                with dest.open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            return dest.exists() and dest.stat().st_size > 0
        except Exception as e:
            log.warning("wikimedia dl err %s", e)
            return False