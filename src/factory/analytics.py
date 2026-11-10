"""Analytics-lite: CSV import, YouTube stats, weekly report."""
from __future__ import annotations
import csv, json
from datetime import datetime, timezone
from pathlib import Path
from .config import project_root
from .db import connect, init_db
from .logging_setup import setup_logging

log = setup_logging("analytics")
ROOT = project_root()
LEDGER_PATH = ROOT / "data" / "published_ledger.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_ledger() -> list:
    """Rows describing every reel that is live on a platform.

    Kept on disk (not only Supabase) because the laptop is the only place with
    the YouTube OAuth credentials, so it is the only reliable analytics source.
    """
    if not LEDGER_PATH.exists():
        return []
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning("ledger read err %s", e)
        return []


def save_ledger(rows: list) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def add_to_ledger(entry: dict) -> bool:
    """Record (or update) a published reel. Idempotent on youtube_video_id/reel_id."""
    rows = load_ledger()
    key_id = entry.get("youtube_video_id")
    key_reel = entry.get("reel_id")
    for i, r in enumerate(rows):
        if (key_id and r.get("youtube_video_id") == key_id) or (key_reel and r.get("reel_id") == key_reel):
            rows[i] = {**r, **entry}
            save_ledger(rows)
            return True
    rows.append({**entry, "added_at": _now_iso()})
    save_ledger(rows)
    return True


def refresh_ledger_stats() -> list:
    """Fetch live YouTube statistics for every ledger row that has a video id."""
    rows = load_ledger()
    changed = 0
    for r in rows:
        vid = r.get("youtube_video_id")
        if not vid:
            continue
        try:
            stats = youtube_stats(vid)
        except Exception as e:
            log.warning("yt stats err %s: %s", vid, e)
            stats = None
        if stats:
            r["stats"] = stats
            r["fetched_at"] = _now_iso()
            changed += 1
    if changed:
        save_ledger(rows)
    return rows


def push_analytics(relay_url: str) -> dict:
    """Refresh stats locally, then publish the ledger + snapshot to relay_state."""
    from . import jobs
    rows = refresh_ledger_stats()
    snapshot = {
        "ts": _now_iso(),
        "items": rows,
        "totals": {
            "views": sum(int((r.get("stats") or {}).get("viewCount") or 0) for r in rows),
            "likes": sum(int((r.get("stats") or {}).get("likeCount") or 0) for r in rows),
            "comments": sum(int((r.get("stats") or {}).get("commentCount") or 0) for r in rows),
        },
        "source": "laptop",
    }
    if relay_url:
        jobs.push_state(relay_url, {"analytics_snapshot": snapshot, "published_ledger": rows})
    return snapshot


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
