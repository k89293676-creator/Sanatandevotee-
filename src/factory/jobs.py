"""Reel job: turn a planned `reels` row into a rendered file and an uploaded relay item.

This is the glue the daemon was missing (`tick()` used to only log "rendering reel").
`build_spec` is pure and unit-tested; `render_reel_row` / `upload_reel` do real work
(heavy: ffmpeg + network) and are exercised by the Heavy Pass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from . import sync, tts
from .config import load_config
from .db import connect
from .logging_setup import setup_logging
from .render import RenderSpec, render_reel, SHIV_KEYWORDS

log = setup_logging("jobs")


def _json_list(raw, default=None) -> list:
    if raw is None:
        return list(default or [])
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        return [str(x) for x in v] if isinstance(v, list) else list(default or [])
    except (json.JSONDecodeError, TypeError):
        return list(default or [])


def build_spec(row: dict, script: dict, verse: dict, total_verses: int, speech) -> RenderSpec:
    """Assemble a RenderSpec from DB rows. Pure: no I/O, no clock, deterministic seed."""
    cfg = load_config()
    hooks = _json_list(script.get("hooks_json"))
    idx = int(row.get("hook_idx") or 0)
    hook = hooks[idx] if 0 <= idx < len(hooks) else (hooks[0] if hooks else verse["devanagari"])
    day = row.get("series_day")
    badge = f"शिव चालीसा | दिन {day}/{total_verses}" if day else "शिव चालीसा"
    cta = []
    if day and day < total_verses:
        cta.append(f"कल: दिन {day + 1}/{total_verses} | फॉलो करें")
    cta.append("फ्री पीडीएफ़ + ऑडियो: लिंक बायो में")
    cta.append("सेव करो, एक भक्त को शेयर करो")
    fmt = row.get("format") or script.get("format") or "meaning"
    return RenderSpec(
        uuid=row["uuid"],
        speech=speech,
        hook=hook,
        badge=badge,
        narration=script["narration_hi"],
        cta_lines=cta,
        style=row.get("visual_style") or "golden_diya",
        strategy=row.get("strategy") or cfg.get("visuals", {}).get("strategy", "mixed_montage"),
        archetype=row.get("hook_style") or "stakes",
        model="groq",
        profile=row.get("render_profile") or cfg.get("render", {}).get("profile", "standard"),
        keywords=_json_list(script.get("visual_keywords_json"), SHIV_KEYWORDS),
        image_prompts=_json_list(script.get("image_prompts_json")),
        roman=verse.get("roman") if fmt == "recital" else None,
        seed=int(hashlib.sha256(str(row["uuid"]).encode()).hexdigest()[:8], 16),
    )


def _mark(conn, uuid: str, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE reels SET {cols} WHERE uuid=?", (*fields.values(), uuid))
    conn.commit()


def render_reel_row(row, conn=None) -> dict:
    """Render one planned reel. Updates its row to status='rendered'. Raises on hard failure."""
    own = conn is None
    conn = conn or connect()
    try:
        script = conn.execute("SELECT * FROM scripts WHERE id=?", (row["script_id"],)).fetchone()
        verse = conn.execute("SELECT * FROM verses WHERE id=?", (row["verse_id"],)).fetchone()
        if not script or not verse:
            raise RuntimeError(f"missing script/verse for reel {row['uuid']}")
        total = conn.execute("SELECT COUNT(*) c FROM verses WHERE pack=?", (verse["pack"],)).fetchone()["c"]
        speech = tts.synthesize(script["narration_hi"], row["voice"] or "madhur")
        if speech is None:
            raise RuntimeError(f"TTS returned nothing for reel {row['uuid']}")
        spec = build_spec(dict(row), dict(script), dict(verse), total, speech)
        man = render_reel(spec)
        mp4, cover = Path(man["mp4"]), Path(man["cover"])
        _mark(conn, row["uuid"], video_path=str(mp4), cover_path=str(cover),
              duration_s=man["total_s"], sha256=sync.sha256_file(mp4), status="rendered", last_error=None)
        return man
    finally:
        if own:
            conn.close()


def mark_failed(row, reason: str, conn=None) -> None:
    own = conn is None
    conn = conn or connect()
    try:
        attempts = int(row["attempts"] or 0) + 1
        _mark(conn, row["uuid"], status="failed" if attempts >= 3 else "planned",
              attempts=attempts, last_error=str(reason)[:500])
    finally:
        if own:
            conn.close()


def upload_reel(row, manifest: dict, relay_url: str, conn=None) -> bool:
    """Upload mp4+cover, verify the public URLs, enqueue on the relay, mark the row uploaded."""
    own = conn is None
    conn = conn or connect()
    try:
        script = conn.execute("SELECT * FROM scripts WHERE id=?", (row["script_id"],)).fetchone()
        mp4, cover = Path(manifest["mp4"]), Path(manifest["cover"])
        vid = sync.request_upload_target(relay_url, row["uuid"], mp4.name)
        if not vid:
            raise RuntimeError("no signed video URL")
        if not sync.upload_file(vid["url"], mp4):
            raise RuntimeError("video upload failed")
        if not sync.verify_public_url(vid["public_url"], mp4.stat().st_size):
            raise RuntimeError("video not publicly verifiable")
        cover_public = ""
        cov = sync.request_upload_target(relay_url, row["uuid"], cover.name)
        if cov and sync.upload_file(cov["url"], cover, content_type="image/jpeg"):
            cover_public = cov["public_url"]
        caption = script["caption_hi"] if script else ""
        payload = {
            "series_day": row["series_day"],
            "format": row["format"],
            "verse_ref": str(row["verse_id"]),
            "caption": caption,
            "first_comment": "हर हर महादेव",
            "hashtags": _json_list(script["hashtags_json"]) if script else [],
            "video_url": vid["public_url"],
            "cover_url": cover_public,
            "yt_title": caption[:90],
            "yt_description": (script["caption_roman"] if script else ""),
            "duration_s": manifest["total_s"],
            "scheduled_at": row["scheduled_at_utc"],
            "is_reserve": bool(row["is_reserve"]),
            "status": "scheduled",
            "hook_style": row["hook_style"],
            "visual_style": row["visual_style"],
            "voice": row["voice"],
            "slot_label": row["slot_label"],
        }
        if not sync.enqueue(relay_url, payload):
            raise RuntimeError("enqueue rejected")
        # Event-driven handoff: notify Make.com directly when configured.
        import os, httpx
        webhook_url = os.environ.get("MAKE_WEBHOOK_URL")
        if webhook_url:
            try:
                wh_payload = {
                    "reel_id": row["uuid"],
                    "video_url": vid["public_url"],
                    "caption": caption,
                    "first_comment": "Har Har Mahadev",
                    "insight_media_id": None,
                }
                httpx.post(webhook_url, json=wh_payload, timeout=30)
            except Exception as e:
                log.warning("make webhook dispatch failed: %s", e)
        _mark(conn, row["uuid"], status="uploaded", remote_video_url=vid["public_url"],
              remote_cover_url=cover_public, last_error=None)
        from . import cleanup
        cleanup.cleanup_work_dir(row["uuid"])
        return True
    finally:
        if own:
            conn.close()
