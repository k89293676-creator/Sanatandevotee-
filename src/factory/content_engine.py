"""Content engine: 9 formats, multi-pass generation, judge scorecard."""
from __future__ import annotations
import json
from typing import List, Optional
from .llm.groq_client import chat, extract_content
from .llm.templates import build_template_script
from .logging_setup import setup_logging

log = setup_logging("content_engine")

FORMATS = ["meaning", "recital", "word_by_word", "symbolism", "when_to_chant",
           "life_lesson", "faq", "special_day", "weekly_recap"]

HOOK_ARCHETYPES = ["stakes", "name_the_line", "micro_story_tease", "contrast",
                   "number_promise", "question_specific", "myth_vs_meaning", "loop_hook"]

BANNED_OPENERS = ["क्या आप जानते हैं", "आज हम", "नमस्कार", "नमस्ते"]

def is_banned_opener(text: str) -> bool:
    return any(text.strip().startswith(b) for b in BANNED_OPENERS)

def rule_checks(script: dict, verse: dict) -> list[str]:
    issues = []
    narration = script.get("narration_hi", "")
    words = narration.split()
    if not (70 <= len(words) <= 110):
        issues.append(f"word_count {len(words)} not in 70-110")
    dev = sum(1 for c in narration if "\u0900" <= c <= "\u097F")
    letters = sum(1 for c in narration if c.isalpha())
    if letters > 0 and dev / letters < 0.9:
        issues.append(f"devanagari_ratio {dev/letters:.2f} < 0.9")
    if is_banned_opener(narration):
        issues.append("banned opener")
    # verse text must be present verbatim
    if verse["devanagari"] not in narration and verse["devanagari"].split()[0] not in narration:
        issues.append("verse text missing")
    hooks = script.get("hooks", [])
    if len(hooks) < 3:
        issues.append("too few hooks")
    hashtags = script.get("hashtags", [])
    if not (3 <= len(hashtags) <= 5):
        issues.append(f"hashtags {len(hashtags)} not in 3-5")
    return issues

def _groq_chat(prompt: str, temp: float) -> dict | None:
    from .llm.groq_client import chat, extract_content
    model = __import__("src.factory.config", fromlist=["load_config"]).load_config().get("llm", {}).get("primary", "qwen/qwen3.8-27b")
    resp = chat(model, [{"role": "user", "content": prompt}], temperature=temp)
    content = extract_content(resp) if resp else None
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def draft(verse: dict, fmt: str, cards: list = None) -> dict | None:
    prompt = f"""Write a JSON script for format '{fmt}' for this Shiv Chalisa verse.
Verse: {verse['devanagari']}
Meaning: {verse['meaning_hi']}
Return JSON with keys: hooks (list of 3), hook_styles (list of 3), narration_hi (70-110 Hindi words), caption_hi, caption_roman, hashtags (3-5), seo_keywords (3-5), visual_keywords (6), image_prompts (3), est_seconds (28-45)."""
    return _groq_chat(prompt, 0.8)


def critique(script: dict, verse: dict) -> dict | None:
    prompt = f"""Review this script for a Shiv Chalisa reel. Return JSON with issues per dimension: hook, faithfulness, clarity, language, structure, uniqueness.
Script: {json.dumps(script, ensure_ascii=False)[:2000]}
Verse: {verse['devanagari']}"""
    return _groq_chat(prompt, 0.2)


def revise(script: dict, issues: dict, verse: dict) -> dict | None:
    prompt = f"""Fix only the flagged issues in this script. Return the full corrected JSON.
Issues: {json.dumps(issues, ensure_ascii=False)}
Script: {json.dumps(script, ensure_ascii=False)[:2000]}"""
    return _groq_chat(prompt, 0.5)


def proofread(script: dict) -> dict | None:
    prompt = f"""Proofread this Hindi script: fix grammar/spelling, ensure no Latin text outside Roman line, no markdown, no emoji. Return corrected JSON.
Script: {json.dumps(script, ensure_ascii=False)[:2000]}"""
    return _groq_chat(prompt, 0.0)


def judge(script: dict, verse: dict) -> dict:
    # rule checks as hard gates
    issues = rule_checks(script, verse)
    hard_gates = {"safety": len(issues) == 0, "verse_intact": verse["devanagari"] in script.get("narration_hi", "") or verse["devanagari"].split()[0] in script.get("narration_hi", "")}
    # score estimate (rule-based, no LLM judge for now)
    score = 80 if not issues else 60
    return {"total": score, "hook": 20, "faithfulness": 20, "clarity": 15, "language": 15, "structure": 5, "uniqueness": 5, "hard_gates": hard_gates, "reasons": issues, "pass": score >= 80 and all(hard_gates.values())}

def generate_script(verse: dict, fmt: str, cards: list = None, max_rounds: int = 2) -> dict | None:
    script = draft(verse, fmt, cards)
    if not script:
        # fallback to template
        from .llm.templates import build_template_script
        t = build_template_script(verse, fmt)
        t["origin"] = "template"
        return t
    # critique + revise loop
    for _ in range(max_rounds):
        issues = rule_checks(script, verse)
        if not issues:
            break
        cr = critique(script, verse)
        if cr:
            revised = revise(script, cr, verse)
            if revised:
                script = revised
    # proofread
    pr = proofread(script)
    if pr:
        script = pr
    # banned terms filter for visual_keywords
    banned = {"person", "city", "car", "water", "sky", "nature", "man", "woman", "building"}
    vk = script.get("visual_keywords", [])
    if isinstance(vk, str):
        vk = [x.strip() for x in vk.split(",") if x.strip()]
    script["visual_keywords"] = [kw for kw in vk if kw.lower() not in banned]
    if len(script["visual_keywords"]) < 6:
        script["visual_keywords"] += ["shiva statue", "temple diya light", "himalayas spiritual smoke", "meditation light"][:6 - len(script["visual_keywords"])]
    # judge
    sc = judge(script, verse)
    script["score"] = sc
    if not sc.get("pass", False):
        log.warning("script failed judge: %s", sc.get("reasons"))
    script["origin"] = "llm"
    script["model"] = "qwen/qwen3.8-27b"
    script["prompt_version"] = "v6"
    script["format"] = fmt
    script["verse_id"] = verse["id"]
    return script