"""Visuals: Pexels videos, Pollinations stills, Ken Burns, fallbacks."""
from __future__ import annotations
import httpx, random
from pathlib import Path
from .config import media_dir
from .secrets_store import get_secret
from .logging_setup import setup_logging

log = setup_logging("visuals")
CACHE = media_dir() / "cache"
CACHE.mkdir(parents=True, exist_ok=True)


def pexels_search_videos(query: str, orientation: str = "portrait", per_page: int = 5) -> list:
    key = get_secret("PEXELS_API_KEY")
    if not key:
        return []
    try:
        r = httpx.get("https://api.pexels.com/videos/search",
                      headers={"Authorization": key},
                      params={"query": query, "orientation": orientation, "per_page": per_page},
                      timeout=30)
        if r.status_code != 200:
            return []
        return r.json().get("videos", [])
    except Exception as e:
        log.warning("pexels err %s", e)
        return []


def download(url: str, dest: Path) -> bool:
    try:
        with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
            if r.status_code != 200:
                return False
            with dest.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return dest.exists() and dest.stat().st_size > 0
    except Exception as e:
        log.warning("download err %s", e)
        return False


def pollinations_url(prompt: str, seed: int, w: int = 1080, h: int = 1920) -> str:
    import urllib.parse
    q = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{q}?width={w}&height={h}&seed={seed}&nologo=true"


def ken_burns_filter(duration: float, zoom: float = 1.15) -> str:
    # ffmpeg zoompan filter
    frames = int(duration * 30)
    return (f"zoompan=z='min(zoom+0.0015,{zoom})':d={frames}:s=1080x1920:fps=30,"
            f"scale=1080:1920")