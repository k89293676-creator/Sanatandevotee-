"""Persist a generated script plus its judge scorecard.

Before this, `content_engine.generate_script` returned a dict that the daemon only
logged, so `scripts` never grew and `script_scores` stayed empty (the optimizer had
no data). This is the single write path.
"""
from __future__ import annotations

import json
from typing import Optional

from .db import connect
from .logging_setup import setup_logging

log = setup_logging("script_store")


def _j(v) -> str:
    if isinstance(v, str):
        return json.dumps([x.strip() for x in v.split(",") if x.strip()], ensure_ascii=False)
    return json.dumps(list(v or []), ensure_ascii=False)


def save_script(verse: dict, fmt: str, script: dict, conn=None) -> int:
    """Insert the script if new; always upsert its score. Returns the scripts.id.

    An existing (verse, format) row is never overwritten (resume semantics), so the
    returned id may refer to a previously stored script; in that case the old score
    is left untouched to avoid scoring text that is not in the DB.
    """
    own = conn is None
    conn = conn or connect()
    try:
        existing = conn.execute(
            "SELECT id FROM scripts WHERE verse_id=? AND format=?", (verse["id"], fmt)
        ).fetchone()
        if existing:
            return int(existing["id"])
        cur = conn.execute(
            """INSERT INTO scripts (verse_id,format,hooks_json,hook_styles_json,narration_hi,caption_hi,
                                    caption_roman,hashtags_json,seo_keywords_json,visual_keywords_json,
                                    image_prompts_json,est_seconds,status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (verse["id"], fmt, _j(script.get("hooks")), _j(script.get("hook_styles")),
             script.get("narration_hi", ""), script.get("caption_hi", ""),
             script.get("caption_roman", ""), _j(script.get("hashtags")),
             _j(script.get("seo_keywords")), _j(script.get("visual_keywords")),
             _j(script.get("image_prompts")), int(script.get("est_seconds") or 35),
             script.get("origin", "generated")),
        )
        script_id = int(cur.lastrowid)
        sc = script.get("score")
        if isinstance(sc, dict):
            conn.execute(
                """INSERT OR REPLACE INTO script_scores
                   (script_id,total,hook,faithfulness,clarity,language,structure,uniqueness,
                    hard_gates_json,reasons_json,judge_model)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (script_id, int(sc.get("total") or 0), int(sc.get("hook") or 0),
                 int(sc.get("faithfulness") or 0), int(sc.get("clarity") or 0),
                 int(sc.get("language") or 0), int(sc.get("structure") or 0),
                 int(sc.get("uniqueness") or 0),
                 json.dumps(sc.get("hard_gates") or {}, ensure_ascii=False),
                 json.dumps(sc.get("reasons") or [], ensure_ascii=False),
                 str(sc.get("judge_model") or "rules-v1")),
            )
        conn.commit()
        return script_id
    finally:
        if own:
            conn.close()


def score_for(script_id: int, conn=None) -> Optional[dict]:
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM script_scores WHERE script_id=?", (script_id,)).fetchone()
        return dict(row) if row else None
    finally:
        if own:
            conn.close()
