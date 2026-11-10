"""Groq-driven cognitive strategy: ingest performance, analyze, tune prompts, report."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import project_root
from .db import connect, init_db
from .logging_setup import setup_logging
from .secrets_store import get_secret

log = setup_logging("strategy")
ROOT = project_root()
REPORT_PATH = ROOT / "docs" / "WEEKLY_STRATEGY_REPORT.md"


def _supabase() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    return url, key


def ingest_metrics() -> dict:
    """Pull recent performance metrics from Supabase (reel_metrics) + YouTube stats."""
    init_db()
    url, key = _supabase()
    metrics = []
    if url and key:
        try:
            import httpx
            r = httpx.get(f"{url}/rest/v1/reel_metrics?select=*&order=created_at.desc&limit=50",
                          headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=20)
            if r.status_code == 200:
                metrics = r.json() or []
        except Exception as e:
            log.warning("ingest supabase err %s", e)
    # YouTube stats for published reels
    conn = connect()
    rows = conn.execute("SELECT uuid, remote_video_url FROM reels WHERE status='uploaded'").fetchall()
    conn.close()
    yt_stats = {}
    for r in rows:
        vid = (r["remote_video_url"] or "").split("/")[-1]
        if not vid:
            continue
        try:
            from . import analytics
            s = analytics.youtube_stats(vid)
            if s:
                yt_stats[r["uuid"]] = s
        except Exception:
            pass
    return {"supabase_metrics": metrics, "youtube_stats": yt_stats, "count": len(metrics) + len(yt_stats)}


def analyze_and_tune(metrics: dict) -> dict:
    """Groq analyzes metrics and returns tuning recommendations."""
    from .llm.groq_client import chat, extract_content
    import json as _j
    model = "qwen/qwen3.8-27b"
    prompt = f"""You are a social-media growth strategist for a devotional Shiv Chalisa short-form video channel (YouTube Shorts + Instagram Reels).

Recent performance data:
{json.dumps(metrics, ensure_ascii=False)[:6000]}

Analyze what worked: high-performing hook structures, visual pacing traits, caption/hashtag patterns, posting slots.
Return JSON with keys:
- top_hooks: list of hook patterns that performed best
- best_slots: list of best posting slots (IST)
- visual_pacing: recommended shot length / transition notes
- prompt_tuning: object with keys hook_style, narration_tone, cta_style, hashtag_focus (each a short instruction string)
- next_batch_recommendations: list of 5 actionable recommendations
"""
    try:
        resp = chat(model, [{"role": "user", "content": prompt}], temperature=0.4)
        content = extract_content(resp) if resp else None
        if content:
            try:
                return json.loads(content)
            except Exception:
                return {"raw": content}
    except Exception as e:
        log.warning("strategy analyze err %s", e)
    return {}


def apply_tuning(tuning: dict) -> None:
    """Persist tuning recommendations to data/prompt_notes.md (soft guidance)."""
    try:
        notes = ROOT / "data" / "prompt_notes.md"
        notes.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Strategy tuning (auto-generated)", ""]
        pt = tuning.get("prompt_tuning", {}) if isinstance(tuning, dict) else {}
        for k, v in pt.items():
            lines.append(f"- {k}: {v}")
        recs = tuning.get("next_batch_recommendations", []) if isinstance(tuning, dict) else []
        if recs:
            lines.append("")
            lines.append("## Recommendations")
            for r in recs:
                lines.append(f"- {r}")
        notes.write_text("\n".join(lines), encoding="utf-8")
        log.info("strategy tuning written to %s", notes)
    except Exception as e:
        log.warning("apply_tuning err %s", e)


def generate_weekly_report() -> str:
    metrics = ingest_metrics()
    tuning = analyze_and_tune(metrics)
    apply_tuning(tuning)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Weekly Strategy Report — {now}",
        "",
        "## Audience response",
        f"- Supabase metrics ingested: {len(metrics.get('supabase_metrics', []))}",
        f"- YouTube stats fetched: {len(metrics.get('youtube_stats', {}))}",
        "",
        "## Top-performing hooks",
    ]
    top_hooks = tuning.get("top_hooks", []) if isinstance(tuning, dict) else []
    for h in (top_hooks or ["(none yet)"]):
        lines.append(f"- {h}")
    lines.append("")
    lines.append("## Best slots")
    for s in (tuning.get("best_slots", []) if isinstance(tuning, dict) else []):
        lines.append(f"- {s}")
    lines.append("")
    lines.append("## Visual pacing")
    lines.append(str(tuning.get("visual_pacing", "n/a") if isinstance(tuning, dict) else "n/a"))
    lines.append("")
    lines.append("## Recommendations for next batch")
    for r in (tuning.get("next_batch_recommendations", []) if isinstance(tuning, dict) else []):
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## Prompt tuning")
    pt = tuning.get("prompt_tuning", {}) if isinstance(tuning, dict) else {}
    for k, v in pt.items():
        lines.append(f"- **{k}**: {v}")
    text = "\n".join(lines) + "\n"
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(text, encoding="utf-8")
        log.info("weekly report written to %s", REPORT_PATH)
    except Exception as e:
        log.warning("report write err %s", e)
    return text


def strategy_tick() -> dict:
    metrics = ingest_metrics()
    tuning = analyze_and_tune(metrics)
    apply_tuning(tuning)
    return {"metrics_count": metrics.get("count", 0), "tuning_keys": list(tuning.keys()) if isinstance(tuning, dict) else []}