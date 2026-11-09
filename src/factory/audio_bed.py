"""Procedural calm audio bed (drone + bell). Copyright-clean."""
from __future__ import annotations
import numpy as np
from pathlib import Path
import wave, struct

from .config import media_dir
from .logging_setup import setup_logging

log = setup_logging("audio_bed")
OUT = media_dir() / "audio"
OUT.mkdir(parents=True, exist_ok=True)


def generate(duration: float = 40.0, seed: int = 0, sr: int = 44100) -> Path:
    rng = np.random.default_rng(seed)
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # drone: low fundamental + harmonics
    drone = 0.15 * np.sin(2 * np.pi * 110 * t) + 0.08 * np.sin(2 * np.pi * 165 * t)
    # slow LFO
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t)
    drone = drone * lfo
    # bells: sparse damped sinusoids
    bells = np.zeros_like(t)
    for i in range(6):
        start = rng.uniform(2, duration - 2)
        freq = rng.choice([523.25, 659.25, 784.0, 392.0])
        idx = int(start * sr)
        length = int(2.5 * sr)
        if idx + length > len(t):
            continue
        env = np.exp(-np.linspace(0, 4, length))
        waveb = 0.12 * np.sin(2 * np.pi * freq * np.arange(length) / sr) * env
        bells[idx:idx+length] += waveb
    mix = drone + bells
    # normalize background to about -28 LUFS (scale to low volume)
    peak = np.max(np.abs(mix)) or 1
    mix = mix / peak * 0.04  # ~-28 dB
    # fade in 1.5s, fade out 2.0s
    fi = int(1.5 * sr)
    fo = int(2.0 * sr)
    if fi < len(mix):
        mix[:fi] *= np.linspace(0, 1, fi)
    if fo < len(mix):
        mix[-fo:] *= np.linspace(1, 0, fo)
    out = OUT / f"bed_{seed}_{int(duration)}.wav"
    # write wav
    import array
    frames = array.array("h", (int(v * 32767) for v in mix))
    with wave.open(str(out), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames.tobytes())
    return out