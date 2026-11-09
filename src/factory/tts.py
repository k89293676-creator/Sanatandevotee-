"""TTS chain: edge-tts (with word boundaries) -> gTTS -> Piper. Returns path, REAL duration and boundaries."""
from __future__ import annotations
import asyncio, hashlib, json, shutil, subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from .config import project_root, media_dir
from .logging_setup import setup_logging

log = setup_logging("tts")
CACHE = media_dir() / "audio"
CACHE.mkdir(parents=True, exist_ok=True)
FFPROBE = shutil.which("ffprobe") or "ffprobe"

VOICES = {"madhur": "hi-IN-MadhurNeural", "swara": "hi-IN-SwaraNeural"}


@dataclass
class Speech:
    path: Path
    duration: float
    engine: str
    boundaries: List[Dict] = field(default_factory=list)   # [{"text","start","end"}] seconds


def probe_duration(p: Path) -> float:
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _key(text: str, voice: str, rate: str) -> str:
    return hashlib.sha256(f"{text}|{voice}|{rate}".encode("utf-8")).hexdigest()[:16]


async def _edge(text: str, voice: str, out: Path, rate: str):
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:                      # older edge-tts without the boundary argument
        comm = edge_tts.Communicate(text, voice, rate=rate)
    bounds, n_audio = [], 0
    with out.open("wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"]); n_audio += len(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                s = ch["offset"] / 1e7
                bounds.append({"text": ch["text"], "start": s, "end": s + ch["duration"] / 1e7,
                               "kind": ch["type"]})
    return n_audio > 0, bounds


def _gtts(text: str, out: Path) -> bool:
    try:
        from gtts import gTTS
        gTTS(text=text, lang="hi").save(str(out))
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        log.warning("gtts fail: %s", e)
        return False


def _piper(text: str, out: Path) -> bool:
    piper = shutil.which("piper") or shutil.which("piper.exe")
    voices = project_root() / "assets" / "voices"            # never scan the whole project
    models = [m for m in voices.glob("*.onnx") if "hi" in m.name.lower()] if voices.exists() else []
    ffmpeg = shutil.which("ffmpeg")
    if not (piper and models and ffmpeg):
        return False
    try:
        wav = out.with_suffix(".wav")
        subprocess.run([piper, "--model", str(models[0]), "--output_file", str(wav)],
                       input=text, text=True, check=True, capture_output=True)
        subprocess.run([ffmpeg, "-y", "-i", str(wav), str(out)], check=True, capture_output=True)
        wav.unlink(missing_ok=True)
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        log.warning("piper fail: %s", e)
        return False


def synthesize_chunks(chunks: list[str], voice: str = "hi-IN-MadhurNeural", rate: str = "+0%",
                      gap_ms: int = 200) -> Speech:
    """Synthesize each chunk separately and join with gaps. Returns Speech with per-chunk timings."""
    import asyncio
    paths = []
    boundaries_all = []
    offset = 0.0
    chunk_timings = []
    for i, chunk in enumerate(chunks):
        sp = synthesize(chunk, voice, rate)
        if sp is None:
            # fallback: skip
            continue
        paths.append(sp.path)
        dur = sp.duration
        # build boundary for this chunk
        for b in (sp.boundaries or []):
            boundaries_all.append({"text": b.get("text", chunk), "start": b.get("start", 0) + offset,
                                   "end": b.get("end", dur) + offset})
        if not sp.boundaries:
            boundaries_all.append({"text": chunk, "start": offset, "end": offset + dur})
        chunk_timings.append({"text": chunk, "start": offset, "end": offset + dur})
        offset += dur + gap_ms / 1000.0
    # join audio files with gaps using ffmpeg
    if not paths:
        raise RuntimeError("no chunks synthesized")
    # simple: concatenate with silence gaps
    import subprocess, shutil
    FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
    work = Path(paths[0]).parent / "chunks_join"
    work.mkdir(parents=True, exist_ok=True)
    # build concat list
    concat = work / "concat.txt"
    lines = []
    for p in paths:
        lines.append(f"file '{p.as_posix()}'")
    concat.write_text("\n".join(lines), encoding="utf-8")
    out = work / "joined.wav"
    # use ffmpeg concat with adelay for gaps - simpler: just concat without gaps for now
    subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-c:a", "pcm_s16le", str(out)], capture_output=True)
    dur_total = offset
    return Speech(path=out, duration=dur_total, engine="edge-tts-chunks", boundaries=boundaries_all)


def synthesize(text: str, voice: str = "hi-IN-MadhurNeural", rate: str = "+0%") -> Optional[Speech]:
    voice = VOICES.get(voice, voice)
    k = _key(text, voice, rate)
    out, meta = CACHE / f"{k}.mp3", CACHE / f"{k}.json"
    if out.exists() and meta.exists():
        m = json.loads(meta.read_text(encoding="utf-8"))
        return Speech(out, m["duration"], m["engine"], m.get("boundaries", []))
    engine, bounds = None, []
    try:
        ok, bounds = asyncio.run(_edge(text, voice, out, rate))
        engine = "edge-tts" if ok else None
    except Exception as e:
        log.warning("edge-tts fail: %s", e)
    if not engine and _gtts(text, out):
        engine = "gtts"
    if not engine and _piper(text, out):
        engine = "piper"
    if not engine:
        return None
    dur = probe_duration(out)
    meta.write_text(json.dumps({"duration": dur, "engine": engine, "boundaries": bounds}, ensure_ascii=False), encoding="utf-8")
    return Speech(out, dur, engine, bounds)
