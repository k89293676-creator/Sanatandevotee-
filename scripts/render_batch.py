"""Render every planned reel that has no video yet, earliest first.

HEAVY: this calls ffmpeg and TTS for real, so it refuses to start unless
ALLOW_HEAVY=1 (see AGENTS.md rule 11). Nothing here is exercised in the light
test loop; the heavy behaviour is queued in docs/HEAVY_QUEUE.md.

Usage:
    set ALLOW_HEAVY=1
    python scripts/render_batch.py [--limit N] [--upload --relay-url URL]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory import jobs  # noqa: E402
from src.factory.config import media_dir  # noqa: E402,F401 - keeps path assumptions checked
from src.factory.db import connect, init_db  # noqa: E402
from src.factory.logging_setup import setup_logging  # noqa: E402

log = setup_logging("render_batch")


def pending_rows(conn, limit: int | None = None) -> list:
    sql = ("SELECT * FROM reels WHERE status='planned' "
           "AND (video_path IS NULL OR video_path='') ORDER BY scheduled_at_utc")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def render_rows(rows, conn=None) -> tuple[list, list]:
    """Render each row; return ([(row, manifest)], [(row, error)]). Never raises per row."""
    done, failed = [], []
    for row in rows:
        try:
            done.append((row, jobs.render_reel_row(row, conn)))
        except Exception as e:  # one bad reel must not stop the batch
            log.error("render failed %s: %s", row["uuid"], e)
            jobs.mark_failed(row, str(e), conn)
            failed.append((row, str(e)))
    return done, failed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="render at most N reels")
    ap.add_argument("--upload", action="store_true", help="enqueue rendered reels on the relay")
    ap.add_argument("--relay-url", default=os.environ.get("RELAY_URL", ""))
    args = ap.parse_args(argv)

    if os.environ.get("ALLOW_HEAVY") != "1":
        print("render_batch is HEAVY (ffmpeg + TTS). Re-run with ALLOW_HEAVY=1.")
        return 2
    if args.upload and not args.relay_url:
        print("--upload needs --relay-url or RELAY_URL")
        return 2

    init_db()
    conn = connect()
    try:
        rows = pending_rows(conn, args.limit)
        print("to render:", len(rows))
        done, failed = render_rows(rows, conn)
        if args.upload:
            for row, man in list(done):
                try:
                    jobs.upload_reel(row, man, args.relay_url, conn)
                except Exception as e:
                    log.error("upload failed %s: %s", row["uuid"], e)
                    failed.append((row, f"upload: {e}"))
        for row, err in failed:
            print("FAILED", row["uuid"], err)
        print(f"rendered: {len(done)}, failed: {len(failed)}")
        return 0 if not failed else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
