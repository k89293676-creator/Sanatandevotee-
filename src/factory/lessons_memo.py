"""Weekly lessons memo (guarded): Groq summarises optimizer table into prompt_notes.md."""
from __future__ import annotations
from pathlib import Path
from .config import project_root
from .llm.groq_client import chat, extract_content
from .logging_setup import setup_logging

log = setup_logging("lessons_memo")
ROOT = project_root()
NOTES_PATH = ROOT / "data" / "prompt_notes.md"


def generate_lessons_memo(optimizer_summary: str) -> str | None:
    prompt = f"""Summarise these optimizer results into at most 15 bullet rules for better Reel performance.
Rules must be soft guidance only. Never override policy files or verified text.
Optimizer data: {optimizer_summary}
Return plain text bullets."""
    resp = chat("qwen/qwen3.8-27b", [{"role": "user", "content": prompt}], temperature=0.3)
    content = extract_content(resp) if resp else None
    if content:
        NOTES_PATH.write_text(content, encoding="utf-8")
        log.info("lessons memo written to %s", NOTES_PATH)
    return content