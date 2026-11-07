"""Caption timing: edge-tts boundaries -> whisper -> proportional-by-char."""
from __future__ import annotations
import asyncio
from typing import List, Dict


async def edge_boundaries(text: str, voice: str) -> List[Dict]:
    try:
        import edge_tts
        comm = edge_tts.Communicate(text, voice)
        out = []
        async for chunk in comm.stream():
            if chunk["type"] == "WordBoundary":
                out.append({"text": chunk["text"], "start": chunk["offset"] / 1e7, "end": (chunk["offset"] + chunk["duration"]) / 1e7})
        return out
    except Exception:
        return []


def whisper_align(audio_path: str, script: str) -> List[Dict]:
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(audio_path, word_timestamps=True, language="hi")
        words = []
        for s in segs:
            for w in (s.words or []):
                words.append((w.word.strip(), w.start, w.end))
        # align to script chunks via difflib
        import difflib
        script_words = script.split()
        # build chunks
        chunks = []
        # simple: group whisper words into chunks matching script word count
        return proportional_timings(script, words[-1][2] if words else 1.0)
    except Exception:
        return []


def build_timings(text: str, audio_path: str | None = None, voice: str = "hi-IN-MadhurNeural", duration: float = 40.0) -> List[Dict]:
    # 1. edge-tts boundaries
    try:
        b = asyncio.run(edge_boundaries(text, voice))
        if b:
            # group into chunks of up to 5 words
            chunks = split_chunks(text, 5)
            # map boundaries to chunks proportionally by word count
            return proportional_timings(text, b[-1]["end"] if b else duration, 5)
    except Exception:
        pass
    # 2. whisper
    if audio_path:
        w = whisper_align(audio_path, text)
        if w:
            return w
    # 3. proportional
    return proportional_timings(text, duration, 5)


def split_chunks(text: str, max_words: int = 5) -> List[str]:
    words = text.split()
    chunks = []
    cur = []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def proportional_timings(text: str, duration: float, max_words: int = 5) -> List[Dict]:
    chunks = split_chunks(text, max_words)
    total_chars = sum(len(c) for c in chunks) or 1
    t = 0.0
    out = []
    for c in chunks:
        dur = duration * (len(c) / total_chars)
        out.append({"text": c, "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur
    return out


def build_ass(timings: List[Dict], font: str = "Noto Sans Devanagari", fontsize: int = 48,
             width: int = 1080, height: int = 1920) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{fontsize},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def fmt(ts):
        h = int(ts // 3600)
        m = int((ts % 3600) // 60)
        s = ts % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    lines = [header]
    for t in timings:
        lines.append(f"Dialogue: 0,{fmt(t['start'])},{fmt(t['end'])},Default,,0,0,0,,{t['text']}")
    return "\n".join(lines)