"""Light tests: chunk joining inserts real silence so reported duration matches the file."""
from pathlib import Path
import sys, wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory.tts import _join_with_gaps, probe_duration  # noqa: E402


def _silence(p: Path, seconds: float, rate: int = 44100) -> Path:
    frames = int(rate * seconds)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)
    return p


def test_join_inserts_real_gap(tmp_path):
    a, b = _silence(tmp_path / "a.wav", 0.5), _silence(tmp_path / "b.wav", 0.5)
    out = _join_with_gaps([a, b], gap_ms=200, work=tmp_path / "join")
    assert out.exists()
    assert abs(probe_duration(out) - 1.2) < 0.05      # 0.5 + 0.2 + 0.5


def test_join_zero_gap_is_just_concat(tmp_path):
    a, b = _silence(tmp_path / "a.wav", 0.5), _silence(tmp_path / "b.wav", 0.5)
    out = _join_with_gaps([a, b], gap_ms=0, work=tmp_path / "join")
    assert abs(probe_duration(out) - 1.0) < 0.05


def test_join_single_chunk(tmp_path):
    a = _silence(tmp_path / "a.wav", 0.5)
    out = _join_with_gaps([a], gap_ms=200, work=tmp_path / "join")
    assert abs(probe_duration(out) - 0.5) < 0.05


def test_chunk_boundaries_keep_kind_and_offsets(tmp_path, monkeypatch):
    from src.factory import tts
    from src.factory.tts import Speech

    a, b = _silence(tmp_path / "c1.wav", 0.5), _silence(tmp_path / "c2.wav", 0.5)
    seq = iter([
        Speech(a, 0.5, "fake", [
            {"text": "जय", "start": 0.0, "end": 0.25, "kind": "WordBoundary"},
            {"text": "पंक्ति।", "start": 0.25, "end": 0.5, "kind": "SentenceBoundary"}]),
        Speech(b, 0.5, "fake", [{"text": "हर", "start": 0.1, "end": 0.3, "kind": "WordBoundary"}]),
    ])
    monkeypatch.setattr(tts, "synthesize", lambda text, voice, rate: next(seq))
    sp = tts.synthesize_chunks(["one", "two"], gap_ms=200)
    assert [x.get("kind") for x in sp.boundaries] == ["WordBoundary", "SentenceBoundary", "WordBoundary"]
    assert abs(sp.boundaries[2]["start"] - 0.8) < 0.01      # 0.5 + 0.2 gap + 0.1
    assert abs(sp.duration - 1.2) < 0.05


def test_chunk_without_boundaries_gets_a_word_boundary(tmp_path, monkeypatch):
    from src.factory import tts
    from src.factory.tts import Speech

    a = _silence(tmp_path / "c1.wav", 0.5)
    monkeypatch.setattr(tts, "synthesize", lambda text, voice, rate: Speech(a, 0.5, "fake", []))
    sp = tts.synthesize_chunks(["only"], gap_ms=0)
    assert sp.boundaries == [{"text": "only", "start": 0.0, "end": 0.5, "kind": "WordBoundary"}]
