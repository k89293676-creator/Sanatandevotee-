"""Light tests: render quality is derived from measurements, never a constant."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory import render            # noqa: E402
from src.factory.tts import Speech        # noqa: E402


def _spec(boundaries):
    return render.RenderSpec(
        uuid="score", speech=Speech(Path("voice.mp3"), 2.0, "fake", boundaries),
        hook="", badge="", narration="जय शिव", cta_lines=[],
    )


def test_score_render_uses_measured_values(monkeypatch):
    measured = {"frame_std_mean": 30.0, "scene_changes": 3, "lufs": -14.0,
                "checks": {"a": True, "b": True, "c": False}, "ok": False}
    monkeypatch.setattr(render, "validate", lambda *a, **k: measured)
    bounds = [{"text": "जय", "start": 0.5, "end": 0.8, "kind": "WordBoundary"},
              {"text": "शिव", "start": 1.0, "end": 1.2, "kind": "WordBoundary"}]
    timings = [{"text": "जय", "start": 0.5, "end": 0.8},
               {"text": "शिव", "start": 1.1, "end": 1.2}]
    shots = [{"asset_id": "a", "provider": "pixabay"},
             {"asset_id": "b", "provider": "pixabay"}]
    out = render.score_render(Path("x.mp4"), {"total_s": 2.0, "shots": shots}, timings, _spec(bounds), shots)

    assert out["sync_median_s"] == 0.05           # |0.5-0.5| and |1.1-1.0|
    assert out["sync_max_s"] == 0.1
    assert out["visual_score"] == 80              # 0.6*(30/45) + 0.4*1
    assert out["quality_score"] != 100
    assert 85 <= out["quality_score"] <= 95
    assert out["metrics"]["sync_source"] == "measured"
    assert out["metrics"]["checks_passed"] == 2
    assert out["metrics"]["components"]["coverage"] == 1.0


def test_score_render_flags_unmeasured_sync(monkeypatch):
    measured = {"frame_std_mean": 0.0, "scene_changes": 0, "lufs": None,
                "checks": {"a": False}, "ok": False}
    monkeypatch.setattr(render, "validate", lambda *a, **k: measured)
    timings = [{"text": "जय शिव", "start": 0.0, "end": 1.0}]
    shots = [{"asset_id": "a", "provider": "procedural"}]
    out = render.score_render(Path("x.mp4"), {"total_s": 1.0, "shots": shots}, timings, _spec([]), shots)

    assert out["sync_median_s"] is None and out["sync_max_s"] is None
    assert out["metrics"]["sync_source"] == "unmeasured"
    assert out["quality_score"] < 60              # nothing measured as good


def test_score_render_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ffprobe missing")

    monkeypatch.setattr(render, "validate", boom)
    out = render.score_render(Path("x.mp4"), {"total_s": 1.0, "shots": []}, [], _spec([]), [])
    assert out["quality_score"] is None
    assert "ffprobe missing" in out["metrics"]["error"]
