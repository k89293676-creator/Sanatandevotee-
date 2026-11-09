"""Sync validator: measure caption-cue starts against speech onsets detected in the audio.

Replaces the old script that printed `median_offset_s: 0.1 (estimated)` no matter what.
Exit codes: 0 = PASS, 1 = FAIL, 2 = INCONCLUSIVE (not enough speech onsets to measure).
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TS = re.compile(r"(\d+):(\d\d):(\d\d\.\d+)")
_SIL_START = re.compile(r"silence_start:\s*([\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*([\d.]+)")


def _seconds(stamp: str) -> float:
    m = _TS.search(stamp.strip())
    if not m:
        return 0.0
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def parse_ass(path: Path) -> list[dict]:
    """Return only the narration cues (style 'Cap'), ignoring hook/badge/CTA layers."""
    cues = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        if parts[3].strip() != "Cap":
            continue
        cues.append({"start": _seconds(parts[1]), "end": _seconds(parts[2]), "text": parts[9]})
    return cues


def speech_onsets(mp4: Path, noise_db: int = -35, min_silence: float = 0.25) -> list[float]:
    """Onsets = 0.0 (if the clip does not open with silence) plus every silence_end."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp4),
                        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = r.stderr
    starts = [float(x) for x in _SIL_START.findall(text)]
    ends = [float(x) for x in _SIL_END.findall(text)]
    onsets = [0.0] if not starts or starts[0] > 0.05 else []
    onsets.extend(e for e in ends if e > 0.05)
    return sorted(set(round(o, 3) for o in onsets))


def pair_offsets(cue_starts: list[float], onsets: list[float]) -> list[float]:
    """Signed offset (cue_start - nearest_onset) for each cue, in seconds."""
    if not onsets:
        return []
    return [round(c - min(onsets, key=lambda o: abs(c - o)), 3) for c in cue_starts]


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: check_sync.py <mp4> <ass>")
        return 1
    mp4, ass = Path(sys.argv[1]), Path(sys.argv[2])
    for p in (mp4, ass):
        if not p.exists():
            print(f"missing: {p}")
            return 1
    cues = parse_ass(ass)
    if not cues:
        print("FAIL: no narration cues found in the .ass")
        return 1
    onsets = speech_onsets(mp4)
    if len(onsets) < 2:
        print(json.dumps({"result": "INCONCLUSIVE", "cues": len(cues), "onsets": onsets,
                          "why": "fewer than 2 speech onsets; cannot measure alignment"}, ensure_ascii=False))
        return 2
    offsets = [abs(o) for o in pair_offsets([c["start"] for c in cues], onsets)]
    matched = sum(1 for o in offsets if o <= 0.75) / len(offsets)
    med, mx = round(_median(offsets), 3), round(max(offsets), 3)
    ok = med <= 0.25 and mx <= 0.75 and matched >= 0.8
    print(json.dumps({
        "result": "PASS" if ok else "FAIL",
        "cues": len(cues), "onsets": len(onsets),
        "median_offset_s": med, "max_offset_s": mx,
        "within_0.75s": round(matched, 2),
        "offsets_s": offsets[:20],
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
