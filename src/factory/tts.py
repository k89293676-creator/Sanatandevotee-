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
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

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


def _join_with_gaps(paths: List[Path], gap_ms: int, work: Path) -> Path:
    """Decode every chunk, append `gap_ms` of silence after each (except the last), concat, write WAV.

    The gap is real audio, so the returned file's duration equals sum(chunk durations) + gaps.
    """
    import subprocess
    n = len(paths)
    work.mkdir(parents=True, exist_ok=True)
    out = work / "joined.wav"
    if n == 1:
        subprocess.run([FFMPEG, "-y", "-i", str(paths[0]), "-c:a", "pcm_s16le", str(out)],
                       check=True, capture_output=True)
        return out
    gap = max(0.0, gap_ms / 1000.0)
    fc = []
    for i in range(n):
        pad = f",apad=pad_dur={gap:.3f}" if (gap > 0 and i < n - 1) else ""
        fc.append(f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=mono{pad}[a{i}]")
    fc.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]")
    inputs: List[str] = []
    for p in paths:
        inputs += ["-i", str(p)]
    r = subprocess.run([FFMPEG, "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[out]",
                        "-c:a", "pcm_s16le", str(out)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"chunk join failed: {r.stderr[-400:]}")
    return out


def synthesize_chunks(chunks: list[str], voice: str = "hi-IN-MadhurNeural", rate: str = "+0%",
                      gap_ms: int = 200) -> Speech:
    """Synthesize each chunk, join with real silence gaps, and report the MEASURED total duration."""
    paths: List[Path] = []
    boundaries_all: List[Dict] = []
    offset = 0.0
    for chunk in chunks:
        sp = synthesize(chunk, voice, rate)
        if sp is None:
            continue
        paths.append(sp.path)
        for b in (sp.boundaries or []):
            item = {"text": b.get("text", chunk), "start": b.get("start", 0) + offset,
                    "end": b.get("end", sp.duration) + offset}
            if b.get("kind"):
                item["kind"] = b["kind"]      # keep SentenceBoundary so cut planning can use it
            boundaries_all.append(item)
        if not sp.boundaries:
            boundaries_all.append({"text": chunk, "start": offset, "end": offset + sp.duration,
                                   "kind": "WordBoundary"})
        offset += sp.duration + gap_ms / 1000.0
    if not paths:
        raise RuntimeError("no chunks synthesized")
    out = _join_with_gaps(paths, gap_ms, Path(paths[0]).parent / "chunks_join")
    # trust the file, not the arithmetic: probe what was actually joined
    dur_total = probe_duration(out)
    if dur_total <= 0:
        raise RuntimeError("joined audio has zero duration")
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
