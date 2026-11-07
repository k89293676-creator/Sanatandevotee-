"""TTS chain: edge-tts -> gTTS -> piper (if available). Cache per line."""
from __future__ import annotations
import asyncio, hashlib, subprocess, shutil
from pathlib import Path
from .config import project_root, media_dir
from .logging_setup import setup_logging

log = setup_logging("tts")
CACHE = media_dir() / "audio"
CACHE.mkdir(parents=True, exist_ok=True)


def _cache_path(text: str, voice: str) -> Path:
    h = hashlib.sha256((text + "|" + voice).encode("utf-8")).hexdigest()[:16]
    return CACHE / f"{h}_{voice}.mp3"


async def _edge(text: str, voice: str, out: Path, rate: str = "+0%") -> bool:
    try:
        import edge_tts
        comm = edge_tts.Communicate(text, voice, rate=rate)
        await comm.save(str(out))
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        log.warning("edge-tts fail: %s", e)
        return False


def _gtts(text: str, out: Path) -> bool:
    try:
        from gtts import gTTS
        gTTS(text=text, lang="hi").save(str(out))
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        log.warning("gtts fail: %s", e)
        return False


def synthesize(text: str, voice: str = "hi-IN-MadhurNeural", rate: str = "+0%") -> Path | None:
    out = _cache_path(text, voice)
    if out.exists():
        return out
    # edge-tts
    try:
        ok = asyncio.run(_edge(text, voice, out, rate))
        if ok:
            return out
    except Exception as e:
        log.warning("edge run err: %s", e)
    # gTTS fallback
    if _gtts(text, out):
        return out
    return None


VOICES = {
    "madhur": "hi-IN-MadhurNeural",
    "swara": "hi-IN-SwaraNeural",
}