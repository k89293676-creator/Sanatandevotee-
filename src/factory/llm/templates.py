"""Deterministic template engine (fallback when LLM unavailable)."""
from __future__ import annotations
import json

def build_template_script(verse: dict, fmt: str) -> dict:
    dev = verse["devanagari"]
    meaning = verse["meaning_hi"]
    hook = "जब सब साथ छोड़ दें, तब शिव चालीसा की ये पंक्ति याद रखिए"
    narration = f"{hook} {dev}. {meaning}. भक्ति और श्रद्धा से चालीसा का पाठ करें. Free PDF + audio: link in bio."
    return {
        "verse_id": verse["id"],
        "format": fmt,
        "hooks": [hook] * 5,
        "hook_styles": ["stakes", "name_the_line", "contrast", "question_specific", "loop_hook"],
        "narration_hi": narration,
        "caption_hi": "शिव चालीसा का अर्थ। Free PDF + audio: link in bio.",
        "caption_roman": "Shiv Chalisa meaning. Free PDF + audio: link in bio.",
        "hashtags": ["#ShivChalisa", "#HarHarMahadev"],
        "seo_keywords": ["shiv chalisa meaning", "arth"],
        "visual_keywords": ["shiva statue", "temple diya light", "himalayas spiritual smoke", "meditation light", "rudraksha beads", "cosmic cosmos nebula"],
        "image_prompts": ["calm temple diya flame", "himalaya mist dawn", "cosmic nebula gold"],
        "est_seconds": 32,
        "origin": "template",
        "model": "template",
        "prompt_version": "v6",
    }