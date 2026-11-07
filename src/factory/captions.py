"""Caption timing: edge-tts boundaries -> whisper -> proportional-by-char."""
from __future__ import annotations
import re
from typing import List, Dict


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