"""Visuals package."""
from __future__ import annotations
import httpx, random, urllib.parse
from pathlib import Path

def pollinations_url(prompt: str, seed: int, w: int = 1080, h: int = 1920) -> str:
    q = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{q}?width={w}&height={h}&seed={seed}&nologo=true"

def download(url: str, dest: Path) -> bool:
    try:
        with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
            if r.status_code != 200:
                return False
            with dest.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return dest.exists() and dest.stat().st_size > 0
    except Exception:
        return False