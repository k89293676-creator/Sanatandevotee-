"""Verse database: load pack, verify, store."""
from __future__ import annotations
import json
import hashlib
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

from .config import data_dir
from .db import connect, init_db
from .logging_setup import setup_logging

log = setup_logging("verses")

PACK_DIR = data_dir() / "packs"


def load_pack(name: str) -> List[Dict[str, Any]]:
    p = PACK_DIR / name / "verses.json"
    if not p.exists():
        raise FileNotFoundError(p)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_verse(v: Dict[str, Any]) -> bool:
    required = ["pack", "seq", "kind", "devanagari", "roman", "meaning_hi", "meaning_en"]
    return all(k in v and str(v[k]).strip() for k in required)


def upsert_verses(pack_name: str, verses: List[Dict[str, Any]]) -> int:
    init_db()
    conn = connect()
    n = 0
    for v in verses:
        if not validate_verse(v):
            log.warning("invalid verse seq=%s", v.get("seq"))
            continue
        conn.execute(
            """INSERT INTO verses (pack,seq,kind,devanagari,roman,meaning_hi,meaning_en,story,symbolism,when_to_chant,source_refs,verified_flag)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(pack,seq) DO UPDATE SET
                 kind=excluded.kind, devanagari=excluded.devanagari, roman=excluded.roman,
                 meaning_hi=excluded.meaning_hi, meaning_en=excluded.meaning_en,
                 story=excluded.story, symbolism=excluded.symbolism,
                 when_to_chant=excluded.when_to_chant, source_refs=excluded.source_refs,
                 verified_flag=excluded.verified_flag""",
            (v["pack"], v["seq"], v["kind"], v["devanagari"], v["roman"], v["meaning_hi"],
             v["meaning_en"], v.get("story"), v.get("symbolism"), v.get("when_to_chant"),
             v.get("source_refs"), int(v.get("verified_flag", 0))),
        )
        n += 1
    conn.commit()
    conn.close()
    return n


def verse_count(pack_name: str) -> int:
    init_db()
    conn = connect()
    r = conn.execute("SELECT COUNT(*) c FROM verses WHERE pack=?", (pack_name,)).fetchone()
    conn.close()
    return int(r["c"]) if r else 0


def get_verses(pack_name: str) -> List[Dict[str, Any]]:
    init_db()
    conn = connect()
    rows = conn.execute("SELECT * FROM verses WHERE pack=? ORDER BY seq", (pack_name,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]