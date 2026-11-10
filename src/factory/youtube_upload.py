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


def upload(video_path: Path, title: str, description: str,
           tags: list[str] | None = None, privacy: str = "public",
           category_id: str = "22") -> str | None:
    """Resumable upload of a Short. Returns the video id, or None on failure.

    `privacy` must be one of public / unlisted / private; callers decide, no default
    side-stepping of the human gate beyond the explicit `public` asked for here.
    """
    token = refresh_access_token()
    if not token:
        return None
    snippet: dict = {"title": title[:100], "description": description,
                     "categoryId": category_id}
    if tags:
        snippet["tags"] = tags[:15]
    # init resumable session
    init = httpx.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4"},
        json={"snippet": snippet,
              "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}},
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
        return r.json().get("id")
    log.warning("yt upload fail %s %s", r.status_code, r.text[:400])
    return None


def post_first_comment(video_id: str, text: str) -> str | None:
    """Post the pinned engagement comment. Needs the youtube.force-ssl scope.

    Returns the comment id, or None when the token lacks the scope / the call fails.
    """
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