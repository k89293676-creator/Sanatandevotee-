"""SQLite (WAL) factory working store."""
from __future__ import annotations
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "factory.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS verses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pack TEXT NOT NULL,
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL,
  devanagari TEXT NOT NULL,
  roman TEXT NOT NULL,
  meaning_hi TEXT NOT NULL,
  meaning_en TEXT NOT NULL,
  story TEXT,
  symbolism TEXT,
  when_to_chant TEXT,
  source_refs TEXT,
  verified_flag INTEGER DEFAULT 0,
  UNIQUE(pack, seq)
);
CREATE TABLE IF NOT EXISTS scripts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  verse_id INTEGER NOT NULL REFERENCES verses(id),
  format TEXT NOT NULL,
  hooks_json TEXT NOT NULL,
  hook_styles_json TEXT NOT NULL,
  narration_hi TEXT NOT NULL,
  caption_hi TEXT NOT NULL,
  caption_roman TEXT NOT NULL,
  hashtags_json TEXT NOT NULL,
  seo_keywords_json TEXT NOT NULL,
  visual_keywords_json TEXT NOT NULL,
  image_prompts_json TEXT NOT NULL,
  est_seconds INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'generated',
  UNIQUE(verse_id, format)
);
CREATE TABLE IF NOT EXISTS reels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid TEXT NOT NULL UNIQUE,
  verse_id INTEGER,
  script_id INTEGER,
  format TEXT,
  hook_idx INTEGER,
  hook_style TEXT,
  voice TEXT,
  visual_style TEXT,
  slot_label TEXT,
  series_day INTEGER,
  is_reserve INTEGER DEFAULT 0,
  scheduled_at_utc TEXT,
  status TEXT NOT NULL DEFAULT 'planned',
  video_path TEXT,
  cover_path TEXT,
  duration_s REAL,
  sha256 TEXT,
  remote_video_url TEXT,
  remote_cover_url TEXT,
  attempts INTEGER DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  backend TEXT DEFAULT 'make_com',
  render_profile TEXT DEFAULT 'standard'
);
CREATE TABLE IF NOT EXISTS arms (
  arm_type TEXT NOT NULL,
  arm_key TEXT NOT NULL,
  alpha REAL NOT NULL DEFAULT 1.0,
  beta REAL NOT NULL DEFAULT 1.0,
  n INTEGER NOT NULL DEFAULT 0,
  last_update TEXT,
  PRIMARY KEY (arm_type, arm_key)
);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL DEFAULT (datetime('now')),
  level TEXT NOT NULL,
  component TEXT NOT NULL,
  message TEXT NOT NULL
);
"""


def init_db(path: Path | None = None) -> None:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()