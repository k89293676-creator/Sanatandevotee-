"""Reel job: turn a planned `reels` row into a rendered file and an uploaded relay item."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from . import sync, tts
from .config import load_config, project_root
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
        attempts = int(row.get("attempts") or 0) + 1 if isinstance(row, dict) else int(row["attempts"] or 0) + 1
        _mark(conn, row["uuid"], status="failed" if attempts >= 3 else "planned",
              attempts=attempts, last_error=str(reason)[:500])
    except Exception:
        pass
    finally:
        if own:
            conn.close()


def upload_reel(row, manifest: dict, relay_url: str, conn=None) -> bool:
    own = conn is None
    conn = conn or connect()
    try:
        if (row.get("status") or "") == "uploaded" and row.get("remote_video_url"):
            log.info("reel %s already uploaded; skipping", row["uuid"])
            return True
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
        hashtags = _json_list(script["hashtags_json"]) if script else []
        first_comment = "Har Har Mahadev! Comment \"SHIVA\" for the free PDF + audio guide."
        payload = {
            "series_day": row["series_day"],
            "format": row["format"],
            "verse_ref": str(row["verse_id"]),
            "caption": caption,
            "first_comment": first_comment,
            "hashtags": hashtags,
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
        webhook_url = os.environ.get("MAKE_WEBHOOK_URL")
        if webhook_url:
            try:
                wh_payload = {
                    "reel_id": row["uuid"],
                    "video_url": vid["public_url"],
                    "caption": caption,
                    "first_comment": first_comment,
                    "hashtags": hashtags,
                    "insight_media_id": None,
                }
                import httpx
                r = httpx.post(webhook_url, json=wh_payload, timeout=30)
                log.info("make webhook dispatched %s", r.status_code)
            except Exception as e:
                log.warning("make webhook dispatch failed: %s", e)
        if os.environ.get("YOUTUBE_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"):
            try:
                from . import youtube_upload
                yt_title = (caption[:90] or "Shiv Chalisa") + " #Shorts"
                yt_desc = (script["caption_roman"] if script else "") or caption
                if "#Shorts" not in yt_desc:
                    yt_desc = yt_desc + "\n\n#Shorts"
                yt_id = youtube_upload.upload(
                    mp4, title=yt_title, description=yt_desc,
                    tags=hashtags, privacy="public", category_id="22",
                    made_for_kids=False)
                if yt_id:
                    perm = youtube_upload.video_permalink(yt_id)
                    youtube_upload.post_first_comment(yt_id, first_comment)
                    youtube_upload.save_reel_youtube(row["uuid"], yt_id, perm)
                    log.info("yt published %s -> %s", row["uuid"], yt_id)
            except Exception as e:
                log.warning("yt auto-publish failed: %s", e)
        _mark(conn, row["uuid"], status="uploaded", remote_video_url=vid["public_url"],
              remote_cover_url=cover_public, last_error=None)
        from . import cleanup
        cleanup.cleanup_work_dir(row["uuid"])
        return True
    finally:
        if own:
            conn.close()


def count_rendered_buffer(conn=None) -> int:
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT COUNT(*) c FROM reels WHERE status='rendered'").fetchone()
        return int(row["c"] if row else 0)
    finally:
        if own:
            conn.close()


def ensure_buffer_floor(min_count: int = 5, relay_url: str = "", conn=None) -> int:
    from . import power
    own = conn is None
    conn = conn or connect()
    rendered = 0
    try:
        while count_rendered_buffer(conn) < min_count:
            if not power.can_render():
                log.info("ensure_buffer_floor: power policy blocks render")
                break
            row = conn.execute(
                "SELECT * FROM reels WHERE status='planned' AND scheduled_at_utc IS NOT NULL "
                "ORDER BY scheduled_at_utc LIMIT 1").fetchone()
            if not row:
                row = conn.execute("SELECT * FROM reels WHERE status='planned' LIMIT 1").fetchone()
            if not row:
                break
            try:
                render_reel_row(row, conn=conn)
                rendered += 1
                # H2 gate: rendered reels must be approved by a human before publishing
                try:
                    sc = conn.execute("SELECT * FROM scripts WHERE id=?", (row["script_id"],)).fetchone()
                    submit_for_approval(dict(row), dict(sc) if sc else None, relay_url, conn=conn)
                except Exception as e:
                    log.warning("buffer submit-for-approval err %s", e)
            except Exception as e:
                log.error("buffer render failed %s: %s", row["uuid"], e)
                mark_failed(row, str(e), conn=conn)
                break
        return rendered
    finally:
        if own:
            conn.close()


def _relay_post_json(relay_url: str, path: str, payload) -> tuple[int, str]:
    """POST a JSON body to the relay worker with the daemon's HMAC headers."""
    import httpx
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = sync.factory_headers("POST", path, body)
    r = httpx.post(f"{relay_url.rstrip('/')}{path}", content=body, headers=headers, timeout=60)
    return r.status_code, r.text[:300]


def push_state(relay_url: str, pairs) -> bool:
    """Push one or more {key, value} rows into Supabase relay_state via the relay worker."""
    if not relay_url:
        return False
    if isinstance(pairs, dict):
        pairs = [{"key": k, "value": v} for k, v in pairs.items()]
    try:
        code, txt = _relay_post_json(relay_url, "/api/factory/state-set", {"items": pairs})
        if code not in (200, 201):
            log.warning("push_state %s -> %s %s", [p.get("key") for p in pairs], code, txt)
            return False
        return True
    except Exception as e:
        log.warning("push_state err %s", e)
        return False


def _reel_video_path(row) -> Optional[Path]:
    """Locate the rendered mp4 for a reel row (video_path column, then renders dir)."""
    root = project_root()
    vp = row.get("video_path") if isinstance(row, dict) else None
    if vp:
        cand = Path(vp)
        if not cand.is_absolute():
            cand = root / cand
        if cand.exists():
            return cand
    for cand in (
        root / "media" / "renders" / f"{row['uuid']}.mp4",
        root / "data" / "work" / str(row["uuid"]) / "out.mp4",
    ):
        if cand.exists():
            return cand
    return None


def _reel_cover_path(row) -> Optional[Path]:
    root = project_root()
    for cand in (
        root / "media" / "covers" / f"{row['uuid']}.jpg",
        root / "media" / "renders" / f"{row['uuid']}.jpg",
    ):
        if cand.exists():
            return cand
    return None


def _upload_preview(relay_url: str, uuid: str, mp4: Path) -> tuple[str, str]:
    """Upload the rendered mp4 (and cover) to Supabase Storage; return (video_url, cover_url)."""
    vid = sync.request_upload_target(relay_url, uuid, mp4.name)
    if not vid:
        raise RuntimeError("no signed upload url (run ensure-bucket / check media bucket)")
    if not sync.upload_file(vid["url"], mp4):
        raise RuntimeError("preview upload failed")
    if not sync.verify_public_url(vid["public_url"], mp4.stat().st_size):
        raise RuntimeError("preview not publicly verifiable")
    cover_url = ""
    cover = _reel_cover_path({"uuid": uuid})
    if cover is not None:
        cov = sync.request_upload_target(relay_url, uuid, cover.name)
        if cov and sync.upload_file(cov["url"], cover, content_type="image/jpeg"):
            cover_url = cov["public_url"]
    return vid["public_url"], cover_url


def submit_for_approval(row, script, relay_url: str, conn=None) -> bool:
    """Upload a rendered preview and put the reel in the dashboard approval queue.

    STATUS: real. Requires a rendered mp4 on disk; the reel is only flipped to
    `pending_approval` after the relay accepted the item and the preview URL is
    publicly fetchable. Approval (H2) is human-only: this function never sets it.
    """
    own = conn is None
    conn = conn or connect()
    try:
        uuid = row["uuid"]
        mp4 = _reel_video_path(row)
        if mp4 is None:
            raise RuntimeError("no rendered file for reel")
        video_url, cover_url = _upload_preview(relay_url, uuid, mp4)
        caption = (script.get("caption_hi") or "") if script else ""
        item = {
            "reel_id": uuid,
            "series_day": (row.get("series_day") if isinstance(row, dict) else None),
            "format": row.get("format"),
            "verse_ref": str(row.get("verse_id") or ""),
            "scheduled_at": row.get("scheduled_at_utc"),
            "duration_s": row.get("duration_s"),
            "video_url": video_url,
            "cover_url": cover_url,
            "caption": caption[:400],
            "script_preview": (script.get("narration_hi") or "")[:600] if script else "",
            "submitted_at": _utc_now(),
        }
        code, txt = _relay_post_json(relay_url, "/api/factory/pending-approval", {"items": [item]})
        if code not in (200, 201):
            raise RuntimeError(f"relay rejected pending item: {code} {txt}")
        _mark(conn, uuid, status="pending_approval", last_error=None,
              remote_video_url=video_url, remote_cover_url=(cover_url or None))
        log.info("reel %s submitted for approval (preview %s)", uuid, video_url)
        return True
    except Exception as e:
        log.warning("submit_for_approval %s err %s", row.get("uuid"), e)
        return False
    finally:
        if own:
            conn.close()


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def sync_approved_reels(relay_url: str, conn=None) -> int:
    """Flip locally pending reels to approved (`rendered`) once the dashboard approves them.

    Approval is recorded by the relay in relay_state.approved_reels; this reads it
    back over the HMAC factory API so the laptop needs no Supabase credentials.
    """
    if not relay_url:
        return 0
    own = conn is None
    conn = conn or connect()
    synced = 0
    try:
        import httpx
        r = httpx.get(f"{relay_url.rstrip('/')}/api/factory/approved",
                      headers=sync.factory_headers("GET", "/api/factory/approved", b""), timeout=20)
        if r.status_code != 200:
            log.warning("sync_approved: relay status %s", r.status_code)
            return 0
        approved_ids = r.json().get("approved", []) or []
        for rid in approved_ids:
            local = conn.execute("SELECT status FROM reels WHERE uuid=?", (rid,)).fetchone()
            if local and local["status"] == "pending_approval":
                _mark(conn, rid, status="rendered", last_error=None)
                synced += 1
                log.info("reel %s approved -> rendered", rid)
        return synced
    except Exception as e:
        log.warning("sync_approved err %s", e)
        return 0
    finally:
        if own:
            conn.close()


def approve_reel(uuid: str, relay_url: str = "", conn=None) -> bool:
    """Approve a reel locally (H2 by a human) and tell the relay to drop it from the queue."""
    own = conn is None
    conn = conn or connect()
    try:
        _mark(conn, uuid, status="rendered", last_error=None)
        if relay_url:
            try:
                code, txt = _relay_post_json(relay_url, "/api/factory/approve", {"uuid": uuid})
                if code not in (200, 201):
                    log.warning("approve relay %s %s", code, txt)
            except Exception as e:
                log.warning("approve relay err %s", e)
        return True
    except Exception as e:
        log.warning("approve_reel err %s", e)
        return False
    finally:
        if own:
            conn.close()


def list_pending_approval(conn=None) -> list:
    own = conn is None
    conn = conn or connect()
    try:
        rows = conn.execute("SELECT * FROM reels WHERE status='pending_approval'").fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def buffer_snapshot(relay_url: str, floor: int = 5, conn=None) -> dict:
    """Build a local buffer snapshot and push it to relay_state for the dashboard."""
    own = conn is None
    conn = conn or connect()
    try:
        counts: dict[str, int] = {}
        for r in conn.execute("SELECT status, COUNT(*) c FROM reels GROUP BY status").fetchall():
            counts[r["status"]] = int(r["c"])
        rows = conn.execute(
            "SELECT uuid, series_day, format, status, scheduled_at_utc, duration_s FROM reels "
            "WHERE status IN ('rendered','pending_approval','planned') "
            "ORDER BY (scheduled_at_utc IS NULL), scheduled_at_utc").fetchall()
        snap = {
            "ts": _utc_now(),
            "floor": floor,
            "rendered": counts.get("rendered", 0),
            "pending_approval": counts.get("pending_approval", 0),
            "planned": counts.get("planned", 0),
            "failed": counts.get("failed", 0),
            "uploaded": counts.get("uploaded", 0),
            "published": counts.get("published", 0),
            "healthy": counts.get("rendered", 0) >= floor,
            "by_status": counts,
            "reels": [dict(r) for r in rows[:20]],
        }
        push_state(relay_url, {"buffer_snapshot": snap})
        return snap
    finally:
        if own:
            conn.close()
