"""Captions: phrase chunking, timing (edge-tts -> whisper -> proportional on REAL audio length), ASS builder.

All on-screen text (hook, badge, captions, CTA) goes through libass. Never ffmpeg drawtext.
"""
from __future__ import annotations
import difflib, re
from typing import Dict, List, Optional

DANDA = re.compile(r"[।॥|]+")


def split_chunks(text: str, max_words: int = 5, min_words: int = 2) -> List[str]:
    """Split at danda first (phrase boundary), then into <=max_words pieces, avoiding 1-word orphans."""
    parts = [p.strip() for p in DANDA.split(text) if p.strip()]
    chunks: List[str] = []
    for p in parts:
        words = p.split()
        n = len(words)
        if n <= max_words:
            chunks.append(" ".join(words))
            continue
        pieces = -(-n // max_words)           # ceil
        size = -(-n // pieces)                # balanced piece size
        for i in range(0, n, size):
            chunks.append(" ".join(words[i:i + size]))
    # merge a trailing 1-word orphan into previous chunk
    merged: List[str] = []
    for c in chunks:
        if merged and len(c.split()) < min_words and len(merged[-1].split()) + len(c.split()) <= max_words + 1:
            merged[-1] += " " + c
        else:
            merged.append(c)
    return merged or [text.strip()]


def proportional_timings(chunks: List[str], duration: float, lead: float = 0.2) -> List[Dict]:
    total = sum(len(c) for c in chunks) or 1
    span = max(0.1, duration - lead)
    t, out = lead, []
    for c in chunks:
        d = span * len(c) / total
        out.append({"text": c, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def timings_from_words(chunks: List[str], words: List[Dict]) -> Optional[List[Dict]]:
    """Map timed words (edge-tts WordBoundary or whisper) onto script chunks via difflib.

    words: [{"text","start","end"}]. Returns None if alignment is too poor to trust.
    """
    if not words:
        return None
    script_tokens = [w for c in chunks for w in c.split()]
    heard = [w["text"].strip() for w in words]
    sm = difflib.SequenceMatcher(a=script_tokens, b=heard, autojunk=False)
    if sm.ratio() < 0.45 and len(words) != len(script_tokens):
        return None
    # time for each script token (interpolate unmatched tokens between matched anchors)
    tok_t: List[Optional[tuple]] = [None] * len(script_tokens)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            tok_t[a + k] = (words[b + k]["start"], words[b + k]["end"])
    if len(words) == len(script_tokens):          # 1:1 (common for WordBoundary)
        tok_t = [(w["start"], w["end"]) for w in words]
    known = [i for i, v in enumerate(tok_t) if v]
    if len(known) < max(2, len(script_tokens) // 3):
        return None
    end_all = words[-1]["end"]
    for i in range(len(tok_t)):
        if tok_t[i]:
            continue
        prev = max([k for k in known if k < i], default=None)
        nxt = min([k for k in known if k > i], default=None)
        t0 = tok_t[prev][1] if prev is not None else 0.0
        t1 = tok_t[nxt][0] if nxt is not None else end_all
        gap = [j for j in range(len(tok_t)) if (prev is None or j > prev) and (nxt is None or j < nxt)]
        step = (t1 - t0) / (len(gap) + 1)
        pos = gap.index(i)
        tok_t[i] = (t0 + step * pos, t0 + step * (pos + 1))
    out, idx = [], 0
    for c in chunks:
        n = len(c.split())
        s, e = tok_t[idx][0], tok_t[idx + n - 1][1]
        out.append({"text": c, "start": round(s, 3), "end": round(e, 3)})
        idx += n
    return _tidy(out)


def _tidy(t: List[Dict], hold: float = 0.15) -> List[Dict]:
    """Make cues contiguous (no flicker gaps) and non-overlapping."""
    for i in range(len(t) - 1):
        t[i]["end"] = round(min(t[i + 1]["start"], t[i]["end"] + hold + 0.35) if t[i + 1]["start"] > t[i]["end"] else t[i + 1]["start"], 3)
    return t


_WHISPER = {}


def whisper_words(audio_path: str) -> List[Dict]:
    try:
        from faster_whisper import WhisperModel
        m = _WHISPER.get("m") or _WHISPER.setdefault("m", WhisperModel("small", device="cpu", compute_type="int8"))
        segs, _ = m.transcribe(audio_path, word_timestamps=True, language="hi")
        return [{"text": w.word.strip(), "start": w.start, "end": w.end} for s in segs for w in (s.words or [])]
    except Exception:
        return []


def build_timings(text: str, audio_seconds: float, audio_path: Optional[str] = None,
                  boundaries: Optional[List[Dict]] = None, max_words: int = 5):
    """Return (timings, method). Order: edge boundaries -> faster-whisper -> proportional (real length)."""
    chunks = split_chunks(text, max_words)
    if boundaries:
        r = timings_from_words(chunks, boundaries)
        if r:
            return r, "edge_boundary"
    if audio_path:
        r = timings_from_words(chunks, whisper_words(audio_path))
        if r:
            return r, "whisper"
    return proportional_timings(chunks, audio_seconds), "proportional"


# ---------------- ASS ----------------
def _ts(x: float) -> str:
    x = max(0.0, x)
    return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"


def _esc(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def wrap_two_lines(text: str, max_chars: int = 20) -> str:
    words = text.split()
    if len(text) <= max_chars or len(words) < 2:
        return text
    best, bi = None, 1
    for i in range(1, len(words)):
        d = abs(len(" ".join(words[:i])) - len(" ".join(words[i:])))
        if best is None or d < best:
            best, bi = d, i
    return " ".join(words[:bi]) + "\n" + " ".join(words[bi:])


def build_ass(timings: List[Dict], total: float, hook: str, badge: str, cta_lines: List[str],
              style: Dict, font: str = "Noto Sans Devanagari", latin_font: str = "DejaVu Sans",
              roman: Optional[str] = None, font_size: int = 68, margin_v: int = 420,
              width: int = 1080, height: int = 1920) -> str:
    """style: {"cap_primary": "&H00FFFFFF", "cap_outline": "&H00000000", "accent": "&H0000C8FF"} (BGR)."""
    prim = style.get("cap_primary", "&H00FFFFFF")
    acc = style.get("accent", "&H0040B0FF")
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{font_size},{prim},&H000000FF,&H00101010,&H99000000,-1,0,0,0,100,100,0,0,3,10,0,2,70,70,{margin_v},1
Style: Hook,{font},84,&H00FFFFFF,&H000000FF,&H00000000,&H66000000,-1,0,0,0,100,100,0,0,1,6,2,8,70,70,330,1
Style: Badge,{font},40,{acc},&H000000FF,&H00000000,&H88000000,-1,0,0,0,100,100,0,0,3,8,0,7,48,48,150,1
Style: Roman,{latin_font},42,&H00DDDDDD,&H000000FF,&H00101010,&H88000000,-1,0,0,0,100,100,0,0,1,4,1,2,70,70,{max(150, margin_v - 150)},1
Style: Cta,{font},60,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,3,10,0,5,70,70,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    L = [hdr]
    L.append(f"Dialogue: 1,{_ts(0)},{_ts(total)},Badge,,0,0,0,,{_esc(badge)}")
    L.append(f"Dialogue: 2,{_ts(0.15)},{_ts(3.0)},Hook,,0,0,0,,{{\\fad(250,350)}}{_esc(wrap_two_lines(hook, 16))}")
    cta_start = max(total - 3.2, 0)
    for t in timings:
        if t["start"] >= cta_start - 0.05:
            continue
        end = min(t["end"], cta_start)
        L.append(f"Dialogue: 0,{_ts(t['start'])},{_ts(end)},Cap,,0,0,0,,{_esc(wrap_two_lines(t['text']))}")
    if roman:
        L.append(f"Dialogue: 0,{_ts(3.2)},{_ts(cta_start)},Roman,,0,0,0,,{_esc(roman)}")
    L.append(f"Dialogue: 3,{_ts(cta_start)},{_ts(total)},Cta,,0,0,0,,{{\\fad(300,0)}}{_esc(chr(10).join(cta_lines))}")
    return "\n".join(L) + "\n"
