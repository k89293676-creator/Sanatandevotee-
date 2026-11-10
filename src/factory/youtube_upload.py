"""YouTube Shorts upload (laptop-side, resumable) + metadata helpers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import httpx

from .logging_setup import setup_logging
from .secrets_store import get_secret

log = setup_logging("youtube_upload")


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    if v:
        return v
    # fall back to keyring ( handled by get_secret )
    return get_secret(name)


def youtube_enabled() -> bool:
    return (_env("YOUTUBE_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")


def refresh_access_token() -> str | None:
    cid = _env("YOUTUBE_CLIENT_ID")
    csec = _env("YOUTUBE_CLIENT_SECRET")
    rt = _env("YOUTUBE_REFRESH_TOKEN")
    if not all([cid, csec, rt]):
        return None
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid, "client_secret": csec,
        "refresh_token": rt, "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code != 200:
        log.warning("yt token refresh fail %s", r.status_code)
        return None
    return r.json().get("access_token")


def short_title(title: str) -> str:
    t = (title or "").strip()
    if "#Shorts" not in t and "#shorts" not in t.lower():
        t = (t + " #Shorts").strip()
    return t[:100]


def short_description(description: str) -> str:
    d = (description or "").strip()
    if "#Shorts" not in d and "#shorts" not in d.lower():
        d = (d + "\n\n#Shorts").strip()
    return d


def upload(video_path: Path, title: str, description: str,
          tags: list[str] | None = None, privacy: str = "public",
          category_id: str = "22", made_for_kids: bool = False) -> str | None:
    """Resumable upload of a Short. Returns the video id, or None on failure.

    Defaults: privacy=public, category=22 (People & Blogs), madeForKids=false,
    #Shorts appended to title and description.
    """
    token = refresh_access_token()
    if not token:
        return None
    snippet: dict = {
        "title": short_title(title),
        "description": short_description(description),
        "categoryId": category_id,
    }
    if tags:
        snippet["tags"] = [t for t in tags if t][:15]
    init = httpx.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4"},
        json={"snippet": snippet,
              "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": bool(made_for_kids)}},
        timeout=30,
    )
    if init.status_code not in (200, 201):
        log.warning("yt init fail %s %s", init.status_code, init.text[:400])
        return None
    upload_url = init.headers.get("Location")
    if not upload_url:
        log.warning("yt init missing Location header")
        return None
    with video_path.open("rb") as f:
        data = f.read()
    r = httpx.put(upload_url, content=data, headers={"Content-Type": "video/mp4"}, timeout=600)
    if r.status_code in (200, 201):
        vid = r.json().get("id")
        if vid:
            log.info("yt uploaded %s", vid)
        return vid
    log.warning("yt upload fail %s %s", r.status_code, r.text[:400])
    return None


def video_permalink(video_id: str) -> str:
    return f"https://youtube.com/shorts/{video_id}"


def post_first_comment(video_id: str, text: str) -> str | None:
    token = refresh_access_token()
    if not token:
        return None
    body = {"snippet": {"videoId": video_id,
                        "topLevelComment": {"snippet": {"textOriginal": text}}}}
    r = httpx.post("https://www.googleapis.com/youtube/v3/commentThreads",
                   params={"part": "snippet"},
                   headers={"Authorization": f"Bearer {token}",
                            "Content-Type": "application/json"},
                   json=body, timeout=60)
    if r.status_code not in (200, 201):
        log.warning("yt comment fail %s %s", r.status_code, r.text[:300])
        return None
    return r.json().get("id")


def save_reel_youtube(uuid: str, video_id: str, permalink: str) -> bool:
    """Persist the YouTube video_id locally (LEDGER) and to Supabase when available."""
    try:
        from . import analytics
        analytics.add_to_ledger({
            "reel_id": uuid,
            "youtube_video_id": video_id,
            "youtube_permalink": permalink,
            "platform": "youtube",
            "published_at": _now_iso(),
        })
    except Exception as e:
        log.warning("local ledger save err %s", e)
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "")
    if not url or not key:
        log.info("supabase not configured; skipping yt metadata persist for %s", uuid)
        return False
    try:
        r = httpx.patch(
            f"{url}/rest/v1/reels?uuid=eq.{uuid}",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"youtube_video_id": video_id, "youtube_permalink": permalink,
                  "youtube_uploaded_at": _now_iso()},
            timeout=30,
        )
        if r.status_code in (200, 204):
            log.info("saved yt metadata for %s", uuid)
            return True
        log.warning("supabase patch fail %s %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("supabase save error: %s", e)
    return False


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()