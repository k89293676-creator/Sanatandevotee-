"""YouTube Shorts upload (laptop-side, resumable)."""
from __future__ import annotations
import httpx
from pathlib import Path
from .secrets_store import get_secret
from .logging_setup import setup_logging

log = setup_logging("youtube_upload")


def refresh_access_token() -> str | None:
    cid = get_secret("YOUTUBE_CLIENT_ID")
    csec = get_secret("YOUTUBE_CLIENT_SECRET")
    rt = get_secret("YOUTUBE_REFRESH_TOKEN")
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


def upload(video_path: Path, title: str, description: str) -> str | None:
    token = refresh_access_token()
    if not token:
        return None
    # init resumable session
    init = httpx.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4"},
        json={"snippet": {"title": title[:100], "description": description, "categoryId": "22"},
              "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}},
        timeout=30,
    )
    if init.status_code not in (200, 201):
        log.warning("yt init fail %s", init.status_code)
        return None
    upload_url = init.headers.get("Location")
    if not upload_url:
        return None
    with video_path.open("rb") as f:
        data = f.read()
    r = httpx.put(upload_url, content=data, headers={"Content-Type": "video/mp4"}, timeout=300)
    if r.status_code in (200, 201):
        return r.json().get("id")
    log.warning("yt upload fail %s", r.status_code)
    return None