"""Render all planned reels lacking video, earliest first."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.db import connect, init_db
from src.factory import render, tts, captions, audio_bed
from src.factory.config import media_dir
import uuid

init_db()
conn = connect()
rows = conn.execute("SELECT * FROM reels WHERE status='planned' AND video_path IS NULL ORDER BY scheduled_at_utc").fetchall()
conn.close()
print("to render:", len(rows))
for r in rows:
    print("render", r["uuid"])