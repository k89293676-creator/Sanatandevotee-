"""Pixabay provider."""
from __future__ import annotations
import httpx, json, time, hashlib
from pathlib import Path
from typing import List
from .base import Asset
from ...secrets_store import get_secret
from ...config import media_dir
from ...logging_setup import setup_logging

log = setup_logging("pixabay")
CACHE_DIR = media_dir() / "cache" / "pixabay"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SEARCH_CACHE = CACHE_DIR / "search_cache.json"


def _load_cache() -> dict:
    if SEARCH_CACHE.exists():
        try:
            return json.loads(SEARCH_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(c: dict):
    SEARCH_CACHE.write_text(json.dumps(c), encoding="utf-8")


def _redact(s: str) -> str:
    import re
    return re.sub(r"key=[A-Za-z0-9-]+", "key=[REDACTED]", s)


class PixabayProvider:
    name = "pixabay"

    def available(self) -> bool:
        return bool(get_secret("PIXABAY_API_KEY"))

    def _key(self) -> str:
        return get_secret("PIXABAY_API_KEY") or ""

    def search(self, keywords: list[str], orientation: str = "vertical", kind: str = "image") -> List[Asset]:
        if not self.available():
            return []
        q = " ".join(keywords)[:100]
        FALLBACKS = ["shiva statue", "temple diya light", "himalayas spiritual smoke", "meditation light"]
        cache = _load_cache()
        cache_key = hashlib.sha256(f"{q}|{orientation}|{kind}".encode()).hexdigest()
        entry = cache.get(cache_key)
        if entry and time.time() - entry["ts"] < 86400:
            return [Asset(**a) for a in entry["assets"]]
        endpoint = "https://pixabay.com/api/videos/" if kind == "video" else "https://pixabay.com/api/"
        params = {"key": self._key(), "q": q, "safesearch": "true", "per_page": 5}
        if kind == "image":
            params["orientation"] = "vertical" if orientation == "portrait" else "horizontal"
        assets = []
        try:
            r = httpx.get(endpoint, params=params, timeout=30)
            if r.status_code == 429:
                log.warning("pixabay 429, backing off")
                time.sleep(5)
                return []
            if r.status_code != 200:
                log.warning("pixabay status %s", r.status_code)
                return []
            data = r.json()
            hits = data.get("hits", [])
            if not hits:
                # fallback to curated devotional terms
                for fb in FALLBACKS:
                    params["q"] = fb
                    r2 = httpx.get(endpoint, params=params, timeout=30)
                    if r2.status_code == 200:
                        hits = r2.json().get("hits", [])
                        if hits:
                            break
            for h in hits:
                if kind == "video":
                    vids = h.get("videos", {})
                    # choose smallest >=720 width
                    chosen = None
                    for size in ["small", "medium", "large", "tiny"]:
                        v = vids.get(size)
                        if v and v.get("width", 0) >= 720:
                            chosen = v
                            break
                    if not chosen and vids:
                        chosen = list(vids.values())[0]
                    if not chosen:
                        continue
                    assets.append(Asset(
                        provider="pixabay", asset_id=str(h.get("id")),
                        url=chosen.get("url"), source_page=h.get("pageURL", ""),
                        uploader=h.get("user", ""), license="Pixabay Content License", kind="video"))
                else:
                    assets.append(Asset(
                        provider="pixabay", asset_id=str(h.get("id")),
                        url=h.get("largeImageURL") or h.get("webformatURL"),
                        source_page=h.get("pageURL", ""), uploader=h.get("user", ""),
                        license="Pixabay Content License", kind="image"))
        except Exception as e:
            log.warning("pixabay err %s", _redact(str(e)))
            return []
        cache[cache_key] = {"ts": time.time(), "assets": [a.__dict__ for a in assets]}
        _save_cache(cache)
        return assets

    def download(self, asset: Asset, dest: Path) -> bool:
        try:
            with httpx.stream("GET", asset.url, timeout=120, follow_redirects=True) as r:
                if r.status_code != 200:
                    return False
                with dest.open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            return dest.exists() and dest.stat().st_size > 0
        except Exception as e:
            log.warning("pixabay dl err %s", _redact(str(e)))
            return False