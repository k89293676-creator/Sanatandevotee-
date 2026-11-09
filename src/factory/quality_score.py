"""Legacy reel quality score (0-100).

STATUS: legacy helper. `render.score_render` is the scorer used by the pipeline;
this function is kept for older callers. Its hard gates now default to False so
it can never auto-approve a reel unless the caller passes measured approvals
(verified text, safety, deny-tag, tofu coverage) explicitly.
"""
from __future__ import annotations


def compute_quality_score(script_score: float = 0, sync_median: float = 1.0,
                          sync_max: float = 1.0, visual_score: float = 0,
                          audio_lufs: float = -14.0, validate_ok: bool = False,
                          strategy_diversity: float = 1.0,
                          safety_ok: bool = False, verified_text: bool = False,
                          no_deny_tag: bool = False, tofu_coverage: bool = False) -> dict:
    # weights: script 30, sync 15, visual 20, audio 10, validate 15, diversity 10
    script_part = min(30, script_score * 0.30)
    sync_part = 15 if sync_median < 0.15 and sync_max < 0.4 else (7 if sync_median < 0.4 else 0)
    visual_part = min(20, visual_score * 0.20)
    audio_part = 10 if -16 <= audio_lufs <= -12 else (5 if -18 <= audio_lufs <= -10 else 0)
    validate_part = 15 if validate_ok else 0
    diversity_part = min(10, strategy_diversity * 10)
    total = script_part + sync_part + visual_part + audio_part + validate_part + diversity_part
    hard_gates = {
        "safety": bool(safety_ok),
        "verified_text": bool(verified_text),
        "no_deny_tag": bool(no_deny_tag),
        "sync_ok": sync_median < 0.4,
        "loudness_ok": -18 <= audio_lufs <= -10,
        "tofu_coverage": bool(tofu_coverage),
    }
    auto_approve = total >= 80 and all(hard_gates.values())
    return {
        "total": round(total, 1),
        "script": round(script_part, 1),
        "sync": sync_part,
        "visual": round(visual_part, 1),
        "audio": audio_part,
        "validate": validate_part,
        "diversity": round(diversity_part, 1),
        "hard_gates": hard_gates,
        "auto_approve": auto_approve,
    }
