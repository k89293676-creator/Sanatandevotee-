"""Benchmark Groq models for content generation."""
from __future__ import annotations
import sys, json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.secrets_store import get_secret
from src.factory.llm.groq_client import list_models, chat, extract_content
from src.factory.verses import get_verses

def score(text: str) -> dict:
    # rule checks: devanagari ratio, word count, json validity
    dev = sum(1 for c in text if "\u0900" <= c <= "\u097F")
    letters = sum(1 for c in text if c.isalpha())
    ratio = dev / max(letters, 1)
    words = len(text.split())
    return {"devanagari_ratio": round(ratio, 3), "word_count": words, "ok": ratio > 0.5 and 50 <= words <= 120}

def main():
    models = list_models()
    # prefer text models (exclude whisper, tts, guard)
    candidates = [m for m in models if "whisper" not in m and "tts" not in m and "guard" not in m and "orpheus" not in m]
    print("candidates:", candidates)
    verses = get_verses("shiv_chalisa")[:3]
    results = {}
    for m in candidates:
        scores = []
        t0 = time.time()
        for v in verses:
            for fmt in ["meaning", "recital"]:
                resp = chat(m, [{"role": "user", "content": f"Write a 70-110 word Hindi devotional narration for: {v['devanagari']}"}], temperature=0.8, json_mode=False)
                content = extract_content(resp) if resp else None
                if content:
                    sc = score(content)
                    scores.append(sc)
        elapsed = time.time() - t0
        if scores:
            avg_ok = sum(1 for s in scores if s["ok"]) / len(scores)
            results[m] = {"n": len(scores), "ok_rate": round(avg_ok, 2), "time_s": round(elapsed, 1)}
        else:
            results[m] = {"n": 0, "ok_rate": 0, "time_s": round(elapsed, 1)}
    print(json.dumps(results, indent=2, ensure_ascii=False))
    # write LLM_BENCH.md
    lines = ["# LLM Benchmark", "", "| Model | Samples | OK rate | Time (s) |", "|---|---|---|---|"]
    for m, r in results.items():
        lines.append(f"| {m} | {r['n']} | {r['ok_rate']} | {r['time_s']} |")
    (ROOT / "docs" / "LLM_BENCH.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote docs/LLM_BENCH.md")

if __name__ == "__main__":
    main()