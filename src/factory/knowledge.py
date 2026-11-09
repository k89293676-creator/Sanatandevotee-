"""Knowledge cards: fetch reputable pages, write factual notes."""
from __future__ import annotations
import httpx
from pathlib import Path
from .logging_setup import setup_logging

log = setup_logging("knowledge")
KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge"

ELEMENTS = ["moon", "ganga", "serpent", "trident", "damaru", "ash", "tiger skin", "nandi",
            "kailash", "parvati", "ganesha", "kartikeya", "neelkantha", "tripurantaka"]

def fetch_card(element: str) -> dict | None:
    url = f"https://en.wikipedia.org/wiki/{element.replace(' ', '_')}"
    try:
        r = httpx.get(url, timeout=20, headers={"User-Agent": "ChalisaBot/1.0"})
        if r.status_code != 200:
            return None
        # extract first paragraph
        import re
        text = r.text
        m = re.search(r"<p>(.*?)</p>", text, re.S)
        notes = m.group(1) if m else ""
        notes = re.sub(r"<[^>]+>", "", notes)[:500]
        return {"element": element, "notes": notes, "confidence": 0.7, "source_url": url}
    except Exception as e:
        log.warning("fetch_card err %s", e)
        return None

def generate_cards():
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    for el in ELEMENTS:
        card = fetch_card(el)
        if card:
            path = KNOWLEDGE_DIR / f"{el.replace(' ', '_')}.md"
            path.write_text(f"# {el}\n\n{card['notes']}\n\nSource: {card['source_url']}\n", encoding="utf-8")
            print("card:", el, "OK")
        else:
            print("card:", el, "FAIL")