"""Render pipeline: build MP4 + cover JPEG."""
from __future__ import annotations
import subprocess, shutil, json
from pathlib import Path
from .config import media_dir, project_root
from .logging_setup import setup_logging

log = setup_logging("render")
RENDERS = media_dir() / "renders"
COVERS = media_dir() / "covers"
RENDERS.mkdir(parents=True, exist_ok=True)
COVERS.mkdir(parents=True, exist_ok=True)
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


def _run(cmd: list) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log.error("ffmpeg fail: %s", r.stderr[-500:])
        return r.returncode == 0
    except Exception as e:
        log.error("run err %s", e)
        return False


def render_reel(uuid: str, audio_path: Path, ass_path: Path, shot_paths: list[Path],
                bed_path: Path, duration: float, hook_text: str, series_badge: str,
                style: str = "cosmic_blue", profile: str = "standard") -> tuple[Path | None, Path | None]:
    work = media_dir() / "work" / uuid
    work.mkdir(parents=True, exist_ok=True)
    out_mp4 = RENDERS / f"{uuid}.mp4"
    out_cover = COVERS / f"{uuid}.jpg"
    # Build concat list of shots with durations
    # Simple: use first shot looped? We'll create a slideshow from shots, each 5s, with Ken Burns via zoompan.
    # For robustness, build an input list file.
    list_file = work / "shots.txt"
    # If no shots, create a gradient background
    if not shot_paths:
        grad = work / "grad.mp4"
        _run([FFMPEG, "-y", "-f", "lavfi", "-i",
              f"color=c=0x1a1a2e:s=1080x1920:d={duration}:r=30",
              "-c:v", "libx264", "-pix_fmt", "yuv420p", str(grad)])
        shot_paths = [grad]
    # Build video from shots: concat with crossfade-ish by just concatenating trimmed
    # We'll generate a base video by looping shots to duration using ffmpeg concat demuxer with durations
    per = duration / len(shot_paths)
    with list_file.open("w") as f:
        for sp in shot_paths:
            f.write(f"file '{sp.as_posix()}'\n")
            f.write(f"duration {per:.3f}\n")
        f.write(f"file '{shot_paths[-1].as_posix()}'\n")
    base_video = work / "base.mp4"
    _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
          "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
          "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base_video)])
    if not base_video.exists():
        return None, None
    # Mix audio: voice + bed ducked
    mixed_audio = work / "audio.m4a"
    # bed duck: simple amix with volume
    _run([FFMPEG, "-y", "-i", str(audio_path), "-i", str(bed_path),
          "-filter_complex", "[1:a]volume=0.15[bed];[0:a][bed]amix=inputs=2:duration=first:dropout_transition=2[a]",
          "-map", "[a]", "-c:a", "aac", "-b:a", "128k", str(mixed_audio)])
    audio_input = mixed_audio if mixed_audio.exists() else audio_path
    # Final: overlay captions (ASS) + vignette + badge text
    # Use subtitles filter with ass file
    try:
        ass_rel = ass_path.relative_to(project_root()).as_posix()
    except Exception:
        ass_rel = ass_path.name
    vf = f"subtitles={ass_rel}:fontsdir=assets/fonts"
    font_path = project_root() / "assets" / "fonts" / "NotoSansDevanagari-Bold.ttf"
    # skip drawtext badge for now (added in polish) to keep filter valid
    cmd = [FFMPEG, "-y", "-i", str(base_video), "-i", str(audio_input),
           "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "23",
           "-maxrate", "3.5M", "-bufsize", "7M", "-c:a", "aac", "-b:a", "128k",
           "-movflags", "+faststart", "-shortest", str(out_mp4)]
    ok = _run(cmd)
    if not ok or not out_mp4.exists():
        return None, None
    # Cover JPEG: first frame + hook text
    _run([FFMPEG, "-y", "-i", str(out_mp4), "-vframes", "1", "-q:v", "2", str(out_cover)])
    # validate duration
    return out_mp4, out_cover


def validate(mp4: Path) -> dict:
    # ffprobe checks
    import json as _j
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=codec_name,width,height,r_frame_rate",
                            "-show_entries", "format=duration,size", "-of", "json", str(mp4)],
                           capture_output=True, text=True)
        info = _j.loads(r.stdout)
        dur = float(info["format"]["duration"])
        size = int(info["format"]["size"])
        stream = info["streams"][0]
        return {"codec": stream["codec_name"], "w": stream["width"], "h": stream["height"],
                "dur": dur, "size": size, "ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}