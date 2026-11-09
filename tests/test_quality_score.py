"""Light tests: the legacy scorer cannot auto-approve without measured gates."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory.quality_score import compute_quality_score  # noqa: E402


def perfect_numbers() -> dict:
    return dict(script_score=100, sync_median=0.05, sync_max=0.2,
                visual_score=100, audio_lufs=-14, validate_ok=True,
                strategy_diversity=1.0)


def test_default_gates_never_auto_approve():
    out = compute_quality_score(**perfect_numbers())
    assert out["total"] == 100
    assert out["auto_approve"] is False
    assert out["hard_gates"]["verified_text"] is False
    assert out["hard_gates"]["safety"] is False


def test_auto_approve_requires_every_explicit_gate():
    out = compute_quality_score(
        **perfect_numbers(),
        safety_ok=True, verified_text=True, no_deny_tag=True, tofu_coverage=True,
    )
    assert out["auto_approve"] is True


def test_loudness_and_sync_gates_are_measured():
    out = compute_quality_score(audio_lufs=-5, sync_median=0.9, **{
        k: v for k, v in perfect_numbers().items() if k not in ("audio_lufs", "sync_median")
    })
    assert out["hard_gates"]["loudness_ok"] is False
    assert out["hard_gates"]["sync_ok"] is False
    assert out["auto_approve"] is False
