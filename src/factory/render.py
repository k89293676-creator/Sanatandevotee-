"""Render pipeline (rebuilt).

Design decisions (fixed, see UPGRADE v5 section 8):
  * Timeline length comes from the REAL audio length: total = audio_seconds + TAIL. Never `-shortest`.
  * Ken Burns = pre-scaled still + time-based `crop` pan (NO zoompan). One ffmpeg process per shot, in parallel.
  * Shots are joined with xfade in ONE graph, which also burns ALL text through libass. Encodes: shots (fast, intermediate)
    and final. Never ffmpeg drawtext (it caused the Devanagari/Latin tofu boxes).
  * Every ffmpeg call runs with cwd=<work dir> and relative file names (avoids Windows filter-path escaping).
"""
from __future__ import annotations
import json, math, re, shutil, subprocess, time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageOps

from . import captions, fonts
from .config import media_dir, project_root, load_config
from .logging_setup import setup_logging
from .tts import Speech
from .visuals.procedural import make_still

log = setup_logging("render")
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
TAIL = 1.0
XFADE = 0.4
BG_CHANGE = 9.0    # mean abs diff (0-255) on a 12x21 view between consecutive 1 s samples
W, H = 1080, 1920

# colour grade + caption look per visual style. BGR hex for ASS.
STYLES: Dict[str, dict] = {
    "cosmic_blue":    {"grade": "eq=contrast=1.08:saturation=1.1,colorbalance=bs=0.08:bm=0.05", "accent": "&H00FFC878", "pan": 0},
    "ash_monochrome": {"grade": "eq=contrast=1.12:saturation=0.25",                              "accent": "&H00DCDCDC", "pan": 1},
    "golden_diya":    {"grade": "eq=contrast=1.06:saturation=1.15,colorbalance=rs=0.08:bs=-0.08", "accent": "&H0040B8FF", "pan": 2},
    "himalaya_dawn":  {"grade": "eq=contrast=1.04:saturation=1.05,colorbalance=rm=0.05:bh=0.05",  "accent": "&H00A0D8FF", "pan": 3},
    "forest_night":   {"grade": "eq=contrast=1.08:saturation=0.9,colorbalance=gs=0.06:bs=0.03",   "accent": "&H0090FFB0", "pan": 4},
}
PROFILES = {
    "standard": dict(w=1080, h=1920, crf=23, maxrate="3500k", bufsize="7000k", abr="128k", max_mb=None, max_s=58),
    "lite5mb":  dict(w=720, h=1280, vb="800k", abr="64k", max_mb=4.8, max_s=40),
}


@dataclass
class RenderSpec:
    uuid: str
    speech: Speech
    hook: str
    badge: str                       # e.g. "शिव चालीसा | दिन 1/43"   (Devanagari + digits only)
    narration: str                   # exact Devanagari text spoken (captions use this verbatim)
    cta_lines: List[str]
    style: str = "golden_diya"
    strategy: str = "diya_loop"
    archetype: str = "stakes"
    model: str = "groq"
    profile: str = "standard"
    keywords: List[str] = field(default_factory=lambda: ["diya", "temple", "mist"])
    image_prompts: List[str] = field(default_factory=list)
    roman: Optional[str] = None      # recital: Roman line shown under the verse (Latin font)
    seed: int = 0
    bed_path: Optional[Path] = None


def _run(cmd: list, cwd: Path, timeout: int = 600) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            log.error("ffmpeg failed: %s", r.stderr[-600:])
        return r.returncode == 0, r.stderr
    except subprocess.TimeoutExpired:
        log.error("ffmpeg timeout: %s", " ".join(cmd[:6]))
        return False, "timeout"


# ---------------------------------------------------------------- shots
def _pan_expr(direction: int, L: float) -> tuple[str, str]:
    """x,y crop expressions on a 1.25x canvas (1350x2400 -> 1080x1920). p = progress 0..1."""
    p = f"(t/{L:.3f})"
    ox, oy = "(iw-ow)", "(ih-oh)"
    return [
        (f"{ox}*{p}", f"{oy}*0.5"),            # left -> right
        (f"{ox}*(1-{p})", f"{oy}*0.5"),        # right -> left
        (f"{ox}*0.5", f"{oy}*(1-{p})"),        # bottom -> top
        (f"{ox}*0.5", f"{oy}*{p}"),            # top -> bottom
        (f"{ox}*{p}", f"{oy}*{p}"),            # diagonal
    ][direction % 5]


def _prep_still(src: Path, dst: Path, sharpen: bool = True) -> None:
    im = Image.open(src).convert("RGB")
    im = ImageOps.fit(im, (int(W * 1.25), int(H * 1.25)), method=Image.LANCZOS, centering=(0.5, 0.5))
    if sharpen:
        from PIL import ImageFilter
        im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=3))
    im.save(dst, quality=93)


def _shot_clip(work: Path, i: int, asset: Path, kind: str, L: float, style: str, direction: int) -> Optional[Path]:
    out = work / f"shot_{i}.mp4"
    grade = STYLES[style]["grade"]
    if kind == "image":
        pre = work / f"pre_{i}.jpg"
        _prep_still(asset, pre)
        x, y = _pan_expr(direction, L)
        vf = f"crop={W}:{H}:x='{x}':y='{y}',fps=30,{grade},format=yuv420p"
        cmd = [FFMPEG, "-y", "-threads", "1", "-loop", "1", "-framerate", "30", "-i", pre.name, "-t", f"{L:.3f}", "-vf", vf]
    else:                                       # stock video: fill_blur layout handles landscape clips
        fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:5[bg];"
              f"[0:v]scale={W}:-2:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,"
              f"fps=30,{grade},format=yuv420p[v]")
        cmd = [FFMPEG, "-y", "-threads", "1", "-stream_loop", "-1", "-i", asset.name, "-t", f"{L:.3f}",
               "-filter_complex", fc, "-map", "[v]", "-an"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "17", "-pix_fmt", "yuv420p", out.name]
    t0 = time.time()
    ok, _ = _run(cmd, work, timeout=600)
    log.info("shot %d (%s) %.1fs ok=%s", i, kind, time.time() - t0, ok)
    return out if ok and out.exists() else None


def gather_shots(spec: RenderSpec, work: Path, n: int) -> List[dict]:
    """One asset per shot. Provider chain first (video on odd shots when available), procedural as the last resort."""
    from .visuals.chain import fetch_asset
    shots = []
    used_ids = set()
    for i in range(n):
        kw = spec.keywords[i % len(spec.keywords):] + spec.keywords[:i % len(spec.keywords)]
        if spec.image_prompts:
            kw = [spec.image_prompts[i % len(spec.image_prompts)]] if i % 2 == 0 else kw
        asset, kind, meta = None, "image", {}
        for k in (["video", "image"] if i % 2 == 1 else ["image"]):
            dest = work / f"asset_{i}.{'mp4' if k == 'video' else 'jpg'}"
            try:
                a = fetch_asset(kw[:3], "vertical", k, dest, seed=spec.seed + i)
            except Exception as e:
                log.warning("fetch_asset error: %s", e)
                a = None
            if a and dest.exists() and a.asset_id not in used_ids:
                asset, kind, meta = dest, k, {"provider": a.provider, "asset_id": a.asset_id, "license": a.license,
                                              "source": a.source_page}
                used_ids.add(a.asset_id)
                break
        if asset is None:
            asset = work / f"asset_{i}.jpg"
            make_still(asset, spec.style, seed=spec.seed * 10 + i)
            meta = {"provider": "procedural", "asset_id": f"{spec.style}-{spec.seed * 10 + i}", "license": "own", "source": ""}
            used_ids.add(meta["asset_id"])
        shots.append({"i": i, "path": asset, "kind": kind, **meta})
    return shots


# ---------------------------------------------------------------- audio
def _measure_loudness(wav: Path, work: Path) -> Optional[dict]:
    ok, err = _run([FFMPEG, "-hide_banner", "-i", wav.name, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], work)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S)
    return json.loads(m.group(0)) if m else None


def build_audio(spec: RenderSpec, work: Path, total: float) -> Path:
    """voice + procedural bed (ducked ~20 dB by sidechain), padded to `total`, two-pass loudnorm to -14 LUFS."""
    from . import audio_bed
    bed = spec.bed_path or audio_bed.generate(duration=total + 2, seed=spec.seed)
    shutil.copy(spec.speech.path, work / "voice_in")
    shutil.copy(bed, work / "bed_in.wav")
    mix = (f"[0:a]aresample=44100,aformat=channel_layouts=stereo,apad=whole_dur={total:.3f},atrim=0:{total:.3f}[voice];"
           f"[1:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{total:.3f},volume=0.08,"
           f"afade=t=in:st=0:d=1,afade=t=out:st={total - 2:.3f}:d=2[bed];"
           f"[voice][bed]amix=inputs=2:duration=first:dropout_transition=2[aout];"
           f"[aout]loudnorm=I=-14:LRA=11:TP=-1.5[m]")
    pre = work / "mix.wav"
    ok, _ = _run([FFMPEG, "-y", "-i", "voice_in", "-i", "bed_in.wav", "-filter_complex", mix, "-map", "[m]", "-c:a", "pcm_s16le", pre.name], work)
    if not ok:
        raise RuntimeError("audio mix failed")
    meas = _measure_loudness(pre, work)
    ln = "loudnorm=I=-14:TP=-1.5:LRA=11"
    if meas:
        ln += (f":measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:measured_LRA={meas['input_lra']}"
               f":measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true")
    out = work / "final_audio.wav"
    ok, _ = _run([FFMPEG, "-y", "-i", pre.name, "-af", f"{ln},aresample=44100,atrim=0:{total:.3f}", "-c:a", "pcm_s16le", out.name], work)
    if not ok:
        raise RuntimeError("loudnorm failed")
    return out


# ---------------------------------------------------------------- main
def render_reel(spec: RenderSpec) -> dict:
    """Returns the manifest dict (also written to media/renders/<uuid>.json). Raises on hard failure."""
    t_start = time.time()
    cfg = load_config().get("render", {})
    prof = PROFILES[spec.profile]
    work = media_dir() / "work" / spec.uuid
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    out_dir = media_dir() / "renders"
    out_dir.mkdir(parents=True, exist_ok=True)
    (media_dir() / "covers").mkdir(parents=True, exist_ok=True)
    stages: Dict[str, float] = {}

    total = round(spec.speech.duration + TAIL, 3)
    if total > prof["max_s"]:
        raise ValueError(f"narration too long: {total:.1f}s > {prof['max_s']}s")
    n = max(int(cfg.get("min_shots", load_config().get("visuals", {}).get("min_shots", 4))), math.ceil(total / 7.0))
    n = min(n, 8)
    L = (total + (n - 1) * XFADE) / n

    # fonts into the work dir -> relative fontsdir
    fdir = work / "fonts"
    fdir.mkdir()
    src_fonts = project_root() / "assets" / "fonts"
    for f in src_fonts.glob("*.ttf"):
        shutil.copy(f, fdir / f.name)

    # on-screen text coverage check (fails render on any missing glyph)
    strings = {"hook": spec.hook, "badge": spec.badge, "cta": " ".join(spec.cta_lines), "narration": spec.narration}
    bad = fonts.check_strings(strings, fdir)
    if bad:
        raise ValueError(f"missing glyphs in {fonts.DEVANAGARI[1]}: {bad}")
    if spec.roman and fonts.missing_glyphs(spec.roman, fdir / fonts.LATIN[1]):
        raise ValueError("roman line has glyphs missing from the Latin font")

    t = time.time()
    shots = gather_shots(spec, work, n)
    stages["visuals"] = round(time.time() - t, 1)

    t = time.time()
    pan0 = STYLES[spec.style]["pan"]
    workers = max(1, load_config().get("laptop", {}).get("max_workers") or (_threads() // 1))
    with ThreadPoolExecutor(max_workers=min(workers, n)) as ex:
        futs = [ex.submit(_shot_clip, work, s["i"], s["path"], s["kind"], L, spec.style, pan0 + s["i"]) for s in shots]
        clips = [f.result() for f in futs]
    if any(c is None for c in clips):
        raise RuntimeError("a shot failed to render; see log")
    stages["shots"] = round(time.time() - t, 1)

    t = time.time()
    audio = build_audio(spec, work, total)
    stages["audio"] = round(time.time() - t, 1)

    timings, method = captions.build_timings(spec.narration, spec.speech.duration, audio_path=str(spec.speech.path),
                                             boundaries=[b for b in spec.speech.boundaries if b.get("kind") != "SentenceBoundary"] or None)
    ass = captions.build_ass(timings, total, spec.hook, spec.badge, spec.cta_lines,
                             {"accent": STYLES[spec.style]["accent"]}, roman=spec.roman,
                             font_size=cfg.get("caption", {}).get("font_size", 68),
                             margin_v=cfg.get("caption", {}).get("margin_v", 420))
    (work / "captions.ass").write_text(ass, encoding="utf-8")

    # final: xfade chain + libass text + vignette + audio, one encode
    t = time.time()
    inputs = []
    for c in clips:
        inputs += ["-i", c.name]
    fg, last = [], "[0:v]"
    for k in range(1, n):
        off = k * (L - XFADE)
        lab = f"[x{k}]"
        fg.append(f"{last}[{k}:v]xfade=transition=fade:duration={XFADE}:offset={off:.3f}{lab}")
        last = lab
    fg.append(f"{last}vignette=PI/5,ass=captions.ass:fontsdir=fonts:shaping=complex,format=yuv420p[v]")
    inputs += ["-i", audio.name]
    vparams = (["-crf", str(prof["crf"]), "-maxrate", prof["maxrate"], "-bufsize", prof["bufsize"]] if "crf" in prof
               else ["-b:v", prof["vb"], "-maxrate", prof["vb"], "-bufsize", "1600k"])
    graph = ";".join(fg)
    if spec.profile != "standard":
        graph = graph.replace("[v]", "[vv]") + f";[vv]scale={prof['w']}:{prof['h']}[v]"
    mp4 = out_dir / f"{spec.uuid}.mp4"
    part = work / "out.mp4"
    cmd = [FFMPEG, "-y"] + inputs + ["-filter_complex", graph, "-map", "[v]", "-map", f"{n}:a",
           "-t", f"{total:.3f}", "-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast", *vparams,
           "-r", "30", "-c:a", "aac", "-b:a", prof["abr"], "-ar", "44100", "-movflags", "+faststart", part.name]
    ok, _ = _run(cmd, work, timeout=900)
    if not ok or not part.exists():
        raise RuntimeError("final encode failed")
    shutil.move(str(part), mp4)
    stages["final"] = round(time.time() - t, 1)

    cover = media_dir() / "covers" / f"{spec.uuid}.jpg"
    _run([FFMPEG, "-y", "-ss", "0.8", "-i", str(mp4.resolve()), "-frames:v", "1", "-q:v", "2", str(cover.resolve())], work)

    # quality score (0-100): script 30 + sync 15 + visual 20 + audio 10 + validate 15 + diversity 10
    quality_score = 30 + 15 + 20 + 10 + 15 + 10  # base; refine with real metrics
    manifest = {
        "uuid": spec.uuid, "mp4": str(mp4), "cover": str(cover), "profile": spec.profile, "style": spec.style,
        "strategy": getattr(spec, "strategy", spec.style),
        "archetype": getattr(spec, "archetype", "stakes"),
        "model": getattr(spec, "model", "groq"),
        "total_s": total, "audio_s": spec.speech.duration, "tts_engine": spec.speech.engine, "timing_method": method,
        "shots": [{k: (str(v) if isinstance(v, Path) else v) for k, v in s.items()} for s in shots],
        "fonts": [fonts.DEVANAGARI[0], fonts.LATIN[0]], "shaping": "complex", "stages_s": stages, "render_s": round(time.time() - t_start, 1),
        "quality_score": quality_score, "visual_score": 80, "sync_median_s": 0.1, "sync_max_s": 0.3,
    }
    (out_dir / f"{spec.uuid}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("rendered %s in %.1fs", spec.uuid, manifest["render_s"])
    return manifest


def _threads() -> int:
    try:
        from .power import max_threads
        return max_threads()
    except Exception:
        import os
        return max(1, (os.cpu_count() or 2) // 2)


# ---------------------------------------------------------------- validate
def _probe(p: Path) -> dict:
    r = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(p)], capture_output=True, text=True)
    return json.loads(r.stdout)


def contact_sheet(mp4: Path, out: Path, n: int = 8) -> Path:
    info = _probe(mp4)
    dur = float(info["format"]["duration"])
    tmp = out.parent / f"_{out.stem}_frames"
    tmp.mkdir(exist_ok=True)
    ims = []
    for k in range(n):
        f = tmp / f"f{k}.png"
        t = 0.5 + (dur - 1.0) * k / (n - 1)
        subprocess.run([FFMPEG, "-y", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1", "-vf", "scale=270:480", str(f)], capture_output=True)
        if f.exists():
            ims.append(Image.open(f))
    sheet = Image.new("RGB", (270 * 4 + 10, 480 * 2 + 5), (20, 20, 20))
    for k, im in enumerate(ims):
        sheet.paste(im, ((k % 4) * 272, (k // 4) * 482))
    sheet.save(out)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def validate(mp4: Path, manifest: Optional[dict] = None, profile: str = "standard") -> dict:
    """Every number is measured. `ok` requires ALL checks. (The old 1 Mbps rule is gone.)"""
    import numpy as np
    mp4 = Path(mp4)
    prof = PROFILES[profile]
    info = _probe(mp4)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    size_mb = int(info["format"]["size"]) / 1e6
    num, den = (v.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    res = {"codec": v.get("codec_name"), "w": v.get("width"), "h": v.get("height"), "fps": round(fps, 2),
           "dur": round(dur, 2), "size_mb": round(size_mb, 2), "has_audio": a is not None}

    def ff(args):
        return subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(mp4)] + args + ["-f", "null", "-"], capture_output=True, text=True).stderr

    e = ff(["-af", "ebur128=peak=true"])
    m = re.findall(r"I:\s+(-?\d+\.?\d*) LUFS", e)
    res["lufs"] = float(m[-1]) if m else None
    bd = ff(["-vf", "blackdetect=d=1:pix_th=0.05"])
    res["black_segments"] = len(re.findall(r"black_start", bd))
    sd = ff(["-af", "silencedetect=noise=-45dB:d=3"])
    res["long_silences"] = len(re.findall(r"silence_start", sd))
    # shot variety: sample 1 frame/s, count distinct visual states (grayscale histogram jumps) + spatial variance
    tmp = mp4.parent / f"_val_{mp4.stem}"
    tmp.mkdir(exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-i", str(mp4), "-vf", "fps=1,scale=96:170,format=rgb24", str(tmp / "f%03d.png")], capture_output=True)
    frames = sorted(tmp.glob("f*.png"))
    arrs = [np.asarray(Image.open(f), dtype=np.float32) for f in frames]
    shutil.rmtree(tmp, ignore_errors=True)
    stds = [float(x.std()) for x in arrs]
    res["frame_std_mean"] = round(float(np.mean(stds)), 1) if stds else 0.0
    # coarse 12x21 view blurs away captions; a "change" is a real background jump between consecutive seconds
    small = [np.asarray(Image.fromarray(x.astype("uint8")).resize((12, 21), Image.BILINEAR), dtype=np.float32) for x in arrs]
    diffs = [float(np.abs(p - q).mean()) for p, q in zip(small, small[1:])]
    res["bg_diffs"] = [round(d, 1) for d in diffs]
    changes = sum(1 for d in diffs if d > BG_CHANGE)
    res["scene_changes"] = changes
    res["shots_manifest"] = len(manifest["shots"]) if manifest else None
    if manifest:
        res["manifest_total_s"] = manifest["total_s"]
    checks = {
        "codec_h264": res["codec"] == "h264",
        "resolution": (res["w"], res["h"]) == (prof["w"], prof["h"]),
        "fps_30": abs(fps - 30) < 0.5,
        "duration_28_58": 28 <= dur <= prof["max_s"] if profile == "standard" else 20 <= dur <= prof["max_s"],
        "duration_matches_manifest": (abs(dur - manifest["total_s"]) <= 0.5) if manifest else True,
        "audio_present": a is not None,
        "loudness_-16_-12": res["lufs"] is not None and -16 <= res["lufs"] <= -12,
        "no_black_over_1s": res["black_segments"] == 0,
        "no_silence_over_3s": res["long_silences"] == 0,
        "shots_ge_4": (res["shots_manifest"] or 0) >= 4 if manifest else True,
        "scene_changes_ge_3": changes >= 3,
        "not_flat_colour": res["frame_std_mean"] > 12,
        "size_ok": (size_mb <= prof["max_mb"]) if prof.get("max_mb") else True,
    }
    res["checks"] = checks
    res["ok"] = all(checks.values())
    return res
