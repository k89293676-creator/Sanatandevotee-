"""One-time batch script generation (resumable)."""
from __future__ import annotations
import json, time, re
from pathlib import Path
from typing import List, Dict, Any
import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import project_root, data_dir
from .db import connect, init_db
from .verses import get_verses
from .secrets_store import get_secret
from .logging_setup import setup_logging

log = setup_logging("scriptgen")

FORMATS = ["meaning", "story", "when", "recital"]


class ScriptOut(BaseModel):
    hooks: List[str] = Field(min_length=5, max_length=5)
    hook_styles: List[str] = Field(min_length=5, max_length=5)
    narration_hi: str
    caption_hi: str
    caption_roman: str
    hashtags: List[str] = Field(min_length=3, max_length=5)
    seo_keywords: List[str]
    visual_keywords: List[str] = Field(min_length=6, max_length=6)
    image_prompts: List[str] = Field(min_length=3, max_length=3)
    est_seconds: int


SAFETY_BAD = ["guaranteed", "cure", "100%", "will heal", "जरूर", "गारंटी", "इलाज", "ठीक हो जाएगा"]


def safety_ok(text: str) -> bool:
    low = text.lower()
    return not any(b.lower() in low for b in SAFETY_BAD)


def _gemini(prompt: str) -> str | None:
    key = get_secret("GEMINI_API_KEY")
    if not key:
        return None
    try:
        r = httpx.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
            params={"key": key},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"responseMimeType": "application/json"}},
            timeout=60,
        )
        if r.status_code != 200:
            log.warning("gemini %s", r.status_code)
            return None
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        log.error("gemini err %s", e)
        return None


def _groq(prompt: str) -> str | None:
    key = get_secret("GROQ_API_KEY")
    if not key:
        return None
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama-3.1-8b-instant",
                  "messages": [{"role": "user", "content": prompt}],
                  "response_format": {"type": "json_object"}},
            timeout=60,
        )
        if r.status_code != 200:
            return None
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.error("groq err %s", e)
        return None


def build_prompt(verse: dict, fmt: str) -> str:
    return f"""You are a devotional content writer. Given a Shiv Chalisa verse, produce a JSON object for a short Instagram Reel script.

Verse (Devanagari): {verse['devanagari']}
Roman: {verse['roman']}
Meaning (Hindi): {verse['meaning_hi']}
Meaning (English): {verse['meaning_en']}

Format: {fmt}  (meaning=explain meaning; story=symbolism/story; when=when devotees chant; recital=recite verse with brief intro)

Requirements:
- narration_hi: 70-120 Hindi words (Devanagari), calm devotional, 28-52s when spoken.
- 5 hooks, each tagged style in hook_styles (question|benefit|story_tease|fear_to_courage|curiosity).
- caption_hi, caption_roman.
- hashtags 3-5, seo_keywords 3-5.
- visual_keywords 6.
- image_prompts 3 (stylised, calm, no real people, no text).
- est_seconds integer 28-52.
- No health-cure, money, guaranteed claims; frame benefits as belief.

Return ONLY valid JSON matching keys: hooks, hook_styles, narration_hi, caption_hi, caption_roman, hashtags, seo_keywords, visual_keywords, image_prompts, est_seconds."""


def generate_one(verse: dict, fmt: str) -> dict | None:
    prompt = build_prompt(verse, fmt)
    for attempt in range(3):
        raw = _gemini(prompt) or _groq(prompt)
        if not raw:
            time.sleep(2)
            continue
        try:
            obj = json.loads(raw)
            s = ScriptOut(**obj)
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("validation fail: %s", e)
            time.sleep(1)
            continue
        if not safety_ok(s.narration_hi + " " + s.caption_hi):
            log.warning("safety filter rejected")
            continue
        return {
            "verse_id": verse["id"],
            "format": fmt,
            "hooks_json": json.dumps(s.hooks, ensure_ascii=False),
            "hook_styles_json": json.dumps(s.hook_styles, ensure_ascii=False),
            "narration_hi": s.narration_hi,
            "caption_hi": s.caption_hi,
            "caption_roman": s.caption_roman,
            "hashtags_json": json.dumps(s.hashtags, ensure_ascii=False),
            "seo_keywords_json": json.dumps(s.seo_keywords, ensure_ascii=False),
            "visual_keywords_json": json.dumps(s.visual_keywords, ensure_ascii=False),
            "image_prompts_json": json.dumps(s.image_prompts, ensure_ascii=False),
            "est_seconds": s.est_seconds,
            "status": "generated",
        }
    return None


def run(pack: str = "shiv_chalisa", resume: bool = True) -> dict:
    init_db()
    verses = get_verses(pack)
    conn = connect()
    done = 0
    skipped = 0
    for v in verses:
        for fmt in FORMATS:
            if resume:
                ex = conn.execute("SELECT id FROM scripts WHERE verse_id=? AND format=?", (v["id"], fmt)).fetchone()
                if ex:
                    skipped += 1
                    continue
            res = generate_one(v, fmt)
            if res:
                try:
                    conn.execute(
                        """INSERT INTO scripts (verse_id,format,hooks_json,hook_styles_json,narration_hi,caption_hi,caption_roman,hashtags_json,seo_keywords_json,visual_keywords_json,image_prompts_json,est_seconds,status)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (res["verse_id"], res["format"], res["hooks_json"], res["hook_styles_json"],
                         res["narration_hi"], res["caption_hi"], res["caption_roman"], res["hashtags_json"],
                         res["seo_keywords_json"], res["visual_keywords_json"], res["image_prompts_json"],
                         res["est_seconds"], res["status"]),
                    )
                    conn.commit()
                    done += 1
                except Exception as e:
                    log.error("insert err %s", e)
            time.sleep(0.5)
    conn.close()
    return {"generated": done, "skipped": skipped}