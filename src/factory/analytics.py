"""Analytics-lite: CSV import, YouTube stats, weekly report."""
from __future__ import annotations
import csv, json
from pathlib import Path
from .config import project_root
from .db import connect, init_db
from .logging_setup import setup_logging

log = setup_logging("analytics")
ROOT = project_root()


def import_insights_csv(csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    init_db()
    conn = connect()
    count = 0
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            media_id = row.get("media_id") or row.get("post_id")
            if not media_id:
                continue
            conn.execute(
                """INSERT INTO kv (key, value, updated_at) VALUES (?, ?, datetime('now'))
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')""",
                (f"insight_{media_id}", json.dumps(row)),
            )
            count += 1
    conn.commit()
    conn.close()
    return count


def youtube_stats(video_id: str) -> dict | None:
    from .secrets_store import get_secret
    import httpx
    cid = get_secret("YOUTUBE_CLIENT_ID")
    csec = get_secret("YOUTUBE_CLIENT_SECRET")
    rt = get_secret("YOUTUBE_REFRESH_TOKEN")
    if not all([cid, csec, rt]):
        return None
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid, "client_secret": csec, "refresh_token": rt, "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code != 200:
        return None
    token = r.json().get("access_token")
    r2 = httpx.get("https://www.googleapis.com/youtube/v3/videos",
                   params={"part": "statistics", "id": video_id},
                   headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r2.status_code == 200:
        items = r2.json().get("items", [])
        if items:
            return items[0].get("statistics", {})
    return None


def weekly_report() -> str:
    init_db()
    conn = connect()
    total = conn.execute("SELECT COUNT(*) FROM reels").fetchone()[0]
    conn.close()
    return f"Weekly report: {total} reels in DB."