"""Light tests: the audio filtergraph really ducks the bed with the voice sidechain."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory.render import audio_mix_graph            # noqa: E402


def test_graph_splits_voice_and_sidechains_the_bed():
    g = audio_mix_graph(40.0)
    assert "asplit=2[voice][key]" in g
    assert "[bed][key]sidechaincompress" in g
    assert "threshold=0.03:ratio=8" in g
    assert "amix=inputs=2:duration=first" in g
    assert "normalize=0" in g
    assert "loudnorm=I=-14" in g
    assert g.rstrip().endswith("[m]")


def test_graph_pads_and_trims_to_real_total():
    g = audio_mix_graph(37.4)
    assert "apad=whole_dur=37.400" in g
    assert "atrim=0:37.400" in g
    assert "afade=t=out:st=35.400:d=2" in g


def test_short_total_never_has_negative_fade_start():
    g = audio_mix_graph(1.0)
    assert "afade=t=out:st=0.000:d=2" in g
