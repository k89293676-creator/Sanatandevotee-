"""Persist a generated script plus its judge scorecard.

Before this, `content_engine.generate_script` returned a dict that the daemon only
logged, so `scripts` never grew and `script_scores` stayed empty (the optimizer had
no data). This is the single write path.
"""
from __future__ import annotations
import json
import os
import time
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
        # Best-effort: persist full judge scorecard to Supabase scripts.judge_scorecard.
        try:
            persist_scorecard_supabase(script_id, verse["id"], fmt, sc)
        except Exception:
            pass
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


def count_planned_scripts(conn=None) -> int:
    """Count scripts not yet rendered into a finished reel (planned state)."""
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) c FROM scripts s LEFT JOIN reels r ON r.script_id=s.id "
            "WHERE r.uuid IS NULL OR r.status IN ('planned','failed')"
        ).fetchone()
        return int(row["c"] if row else 0)
    finally:
        if own:
            conn.close()


def _acquire_lock(key: str, ttl_seconds: int = 300) -> bool:
    """Best-effort distributed lock via Supabase relay_state. Returns True if acquired."""
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    k = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not k:
        return True
    try:
        import httpx
        r = httpx.get(f"{url}/rest/v1/relay_state?key=eq.{key}",
                      headers={"apikey": k, "Authorization": f"Bearer {k}"}, timeout=10)
        now = time.time()
        if r.status_code == 200 and r.json():
            row = r.json()[0]
            try:
                if float(row.get("value", 0)) > now:
                    return False
            except (TypeError, ValueError):
                pass
        httpx.post(f"{url}/rest/v1/relay_state",
                   headers={"apikey": k, "Authorization": f"Bearer {k}",
                            "Content-Type": "application/json",
                            "Prefer": "resolution=merge-duplicates"},
                   json={"key": key, "value": str(now + ttl_seconds)}, timeout=10)
        return True
    except Exception as e:
        log.warning("lock acquire err %s", e)
        return True


def persist_scorecard_supabase(script_id: int, verse_id, fmt: str, scorecard) -> bool:
    """Best-effort: persist the full judge scorecard to Supabase scripts.judge_scorecard JSONB."""
    import os, json
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    k = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not k or scorecard is None:
        return False
    try:
        import httpx
        payload = {"judge_scorecard": scorecard if not isinstance(scorecard, str) else json.loads(scorecard)}
        # Try PATCH by script id; fall back to verse+format match.
        r = httpx.patch(f"{url}/rest/v1/scripts?id=eq.{script_id}",
                        headers={"apikey": k, "Authorization": f"Bearer {k}",
                                 "Content-Type": "application/json", "Prefer": "return=minimal"},
                        json=payload, timeout=20)
        if r.status_code in (200, 204):
            return True
        r2 = httpx.patch(f"{url}/rest/v1/scripts?verse_id=eq.{verse_id}&format=eq.{fmt}",
                         headers={"apikey": k, "Authorization": f"Bearer {k}",
                                  "Content-Type": "application/json", "Prefer": "return=minimal"},
                         json=payload, timeout=20)
        return r2.status_code in (200, 204)
    except Exception as e:
        log.warning("persist_scorecard_supabase err %s", e)
        return False


def _release_lock(key: str) -> None:
    """Release the relay_state advisory lock acquired by `_acquire_lock` (best effort)."""
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    k = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not k:
        return
    try:
        import httpx
        httpx.patch(f"{url}/rest/v1/relay_state?key=eq.{key}",
                    headers={"apikey": k, "Authorization": f"Bearer {k}",
                             "Content-Type": "application/json"},
                    json={"value": "0"}, timeout=10)
    except Exception:
        pass


def ensure_min_scripts(min_count: int = 3, conn=None) -> int:
    """Generate scripts for verses that lack one until at least `min_count` planned scripts exist.

    Uses a Supabase advisory lock so concurrent GA/daemon runs do not duplicate work.
    """
    if not _acquire_lock("script_gen_lock", 300):
        log.info("ensure_min_scripts: lock held by another runner; skipping")
        return 0
    own = conn is None
    conn = conn or connect()
    created = 0
    try:
        from . import content_engine
        all_verses = [dict(r) for r in conn.execute("SELECT * FROM verses ORDER BY seq").fetchall()]
        existing = {r["verse_id"] for r in conn.execute("SELECT verse_id FROM scripts").fetchall()}
        for v in all_verses:
            if count_planned_scripts(conn) >= min_count:
                break
            if v["id"] in existing:
                continue
            try:
                script = content_engine.generate_script(v, "meaning")
                if script:
                    save_script(v, "meaning", script, conn=conn)
                    created += 1
                    existing.add(v["id"])
            except Exception as e:
                log.warning("script gen failed for verse %s: %s", v.get("id"), e)
        conn.commit()
        return created
    finally:
        if own:
            conn.close()
        _release_lock("script_gen_lock")