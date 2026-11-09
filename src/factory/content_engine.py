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
    if not (70 <= len(words) <= 85):
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
Return JSON with keys: hook_text (high-retention 3-second opening line), script_text (70-85 Hindi words, culturally rich authentic Hindi), caption (engaging post copy with clear CTA: comment "SHIVA" to get free PDF guide), hashtags (5-8 high-intent tags), first_comment (automated follow-up comment), visual_keywords (6), image_prompts (3), est_seconds (30-50)."""
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


SAFETY_BAD = ["guaranteed", "cure", "100%", "will heal", "जरूर", "गारंटी", "इलाज", "ठीक हो जाएगा"]
CTA_MARKERS = ["कल", "फॉलो", "लिंक", "सब्सक्राइब", "शेयर", "कमेंट"]
MARKDOWN_CHARS = set("*#`[]{}<>_~")


def _devanagari_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "\u0900" <= c <= "\u097F") / len(letters)


def _sentence_lengths(text: str) -> list[int]:
    import re
    parts = [p.strip() for p in re.split(r"[।॥.?!\n]+", text) if p.strip()]
    return [len(p.split()) for p in parts]


def _bigram_repeat_ratio(text: str) -> float:
    words = text.split()
    if len(words) < 4:
        return 0.0
    grams = list(zip(words, words[1:]))
    return 1.0 - len(set(grams)) / len(grams)


def _score_hook(script: dict) -> tuple[int, list[str]]:
    hooks = script.get("hooks") or []
    styles = script.get("hook_styles") or []
    pts, why = 0, []
    if len(hooks) >= 3:
        pts += 8
    else:
        why.append(f"only {len(hooks)} hooks")
    if hooks and all(3 <= len(str(h).split()) <= 12 for h in hooks):
        pts += 4
    else:
        why.append("hook length outside 3-12 words")
    if len({str(s) for s in styles}) >= 3:
        pts += 4
    else:
        why.append("fewer than 3 distinct hook styles")
    if hooks and not is_banned_opener(str(hooks[0])):
        pts += 4
    elif hooks:
        why.append("banned opener")
    return min(pts, 20), why


def _score_faithfulness(script: dict, verse: dict) -> tuple[int, list[str]]:
    narr = script.get("narration_hi", "")
    verse_text = verse.get("devanagari", "")
    first_line = verse_text.replace("॥", "।").split("।")[0].strip()
    pts, why = 0, []
    if verse_text and verse_text in narr:
        pts += 10
    elif first_line and first_line in narr:
        pts += 8
    else:
        why.append("verse text missing")
    meaning = verse.get("meaning_hi", "")
    tokens = {w for w in meaning.split() if len(w) > 3}
    if tokens:
        overlap = sum(1 for w in tokens if w in narr)
        pts += 4 if overlap >= 2 else (2 if overlap == 1 else 0)
        if overlap < 2:
            why.append("meaning barely reflected")
    else:
        pts += 2
    if verse_text and narr.startswith(verse_text.split()[0] if verse_text.split() else ""):
        pts += 2
    return min(pts, 20), why


def _score_clarity(script: dict) -> tuple[int, list[str]]:
    narr = script.get("narration_hi", "")
    words = len(narr.split())
    pts, why = 0, []
    if 70 <= words <= 110:
        pts += 8
    elif 55 <= words <= 125:
        pts += 4
        why.append(f"word count {words} near range")
    else:
        why.append(f"word count {words} outside 70-110")
    lens = _sentence_lengths(narr)
    if lens and all(4 <= n <= 25 for n in lens):
        pts += 4
    else:
        why.append("sentence length outside 4-25 words")
    if "  " not in narr and narr.strip() == narr:
        pts += 3
    else:
        why.append("stray whitespace")
    return min(pts, 15), why


def _score_language(script: dict) -> tuple[int, list[str]]:
    narr = script.get("narration_hi", "")
    ratio = _devanagari_ratio(narr)
    pts, why = 0, []
    if ratio >= 0.9:
        pts += 10
    elif ratio >= 0.8:
        pts += 5
        why.append(f"devanagari ratio {ratio:.2f}")
    else:
        why.append(f"devanagari ratio {ratio:.2f} < 0.9")
    if not any(c.isascii() and c.isalpha() for c in narr):
        pts += 3
    else:
        why.append("latin letters in Devanagari narration")
    if not any(c in MARKDOWN_CHARS for c in narr):
        pts += 2
    else:
        why.append("markdown characters in narration")
    return min(pts, 15), why


def _score_structure(script: dict) -> tuple[int, list[str]]:
    narr = script.get("narration_hi", "")
    pts, why = 0, []
    if narr and script.get("caption_hi"):
        pts += 4
    else:
        why.append("missing narration or caption")
    tags = script.get("hashtags") or []
    if 3 <= len(tags) <= 5:
        pts += 4
    else:
        why.append(f"hashtags {len(tags)} not in 3-5")
    low = (narr + " " + str(script.get("caption_hi", "")))
    if any(m in low for m in CTA_MARKERS):
        pts += 4
    else:
        why.append("no call to action")
    try:
        est = int(script.get("est_seconds") or 0)
    except (TypeError, ValueError):
        est = 0
    if 28 <= est <= 45:
        pts += 3
    else:
        why.append(f"est_seconds {est} outside 28-45")
    return min(pts, 15), why


def _score_uniqueness(script: dict) -> tuple[int, list[str]]:
    hooks = [str(h) for h in (script.get("hooks") or [])]
    narr = script.get("narration_hi", "")
    pts, why = 0, []
    if hooks and len(set(hooks)) == len(hooks):
        pts += 5
    else:
        why.append("duplicate hooks")
    rep = _bigram_repeat_ratio(narr)
    if rep <= 0.25:
        pts += 5
    else:
        why.append(f"bigram repetition {rep:.2f}")
    first_sentence = narr.replace("॥", "।").split("।")[0].strip()
    if hooks and first_sentence and hooks[0].strip() not in first_sentence:
        pts += 5
    else:
        why.append("hook repeats narration opener")
    return min(pts, 15), why


def judge(script: dict, verse: dict) -> dict:
    """Rule-based, deterministic scorecard. Every dimension is measured from the script text.

    Replaces the old hard-coded `80 if not issues else 60`.
    """
    parts = {
        "hook": _score_hook(script),
        "faithfulness": _score_faithfulness(script, verse),
        "clarity": _score_clarity(script),
        "language": _score_language(script),
        "structure": _score_structure(script),
        "uniqueness": _score_uniqueness(script),
    }
    reasons = [r for _, rs in parts.values() for r in rs]
    total = sum(p for p, _ in parts.values())
    narr = script.get("narration_hi", "")
    caption = script.get("caption_hi", "")
    hard_gates = {
        "safety": not any(b.lower() in (narr + " " + caption).lower() for b in SAFETY_BAD),
        "verse_intact": bool(verse.get("devanagari")) and (
            verse["devanagari"] in narr or
            (verse["devanagari"].split() and verse["devanagari"].split()[0] in narr)
        ),
        "no_banned_opener": bool(narr) and not is_banned_opener(narr),
    }
    return {
        "total": int(total),
        "hook": parts["hook"][0], "faithfulness": parts["faithfulness"][0],
        "clarity": parts["clarity"][0], "language": parts["language"][0],
        "structure": parts["structure"][0], "uniqueness": parts["uniqueness"][0],
        "hard_gates": hard_gates, "reasons": reasons,
        "pass": total >= 80 and all(hard_gates.values()),
        "judge_model": "rules-v1",
    }

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