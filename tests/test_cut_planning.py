"""Light tests: cut times snap to sentence onsets, respect min shot length, and the
xfade chain lands exactly on the real audio length."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory.render import (TRANSITIONS, XFADE, plan_cut_times,       # noqa: E402
                                plan_transitions, sentence_starts_from, shot_lengths)


def test_sentence_starts_come_from_danda_and_word_boundaries():
    words = ["जय", "गिरिजा", "सदा", "करत", "हर", "हर"]
    bounds = [{"text": w, "start": 0.5 * i, "end": 0.5 * i + 0.4, "kind": "WordBoundary"}
              for i, w in enumerate(words)]
    starts = sentence_starts_from(bounds, "जय गिरिजा । सदा करत ॥ हर हर")
    assert starts == [1.0, 2.0]


def test_sentence_starts_handle_latin_full_stop():
    bounds = [{"text": w, "start": float(i), "end": float(i) + 0.5, "kind": "WordBoundary"}
              for i, w in enumerate(["One.", "Two", "three!"])]
    assert sentence_starts_from(bounds, "One. Two three!") == [1.0]


def test_sentence_starts_empty_without_boundaries():
    assert sentence_starts_from([], "जय गिरिजा । सदा") == []


def test_single_shot_has_no_cuts():
    assert plan_cut_times(30.0, 1, [3.0, 9.0]) == []
    assert shot_lengths(30.0, []) == [30.0]
    assert plan_transitions(1) == []


def test_uniform_cuts_without_sentence_boundaries():
    total, n = 40.0, 5
    cuts = plan_cut_times(total, n, [])
    assert len(cuts) == n - 1
    assert cuts == sorted(cuts)
    assert cuts[0] >= 2.5 and cuts[-1] <= total - 2.5
    assert all(b - a >= 2.5 for a, b in zip([0.0] + cuts, cuts))
    assert all(total - c >= 2.5 for c in cuts)


def test_cuts_snap_to_nearest_sentence_start():
    total, n = 40.0, 4                     # desired 10 / 20 / 30
    starts = [2.0, 9.8, 19.6, 30.4, 38.0]
    cuts = plan_cut_times(total, n, starts)
    assert cuts[0] == 9.8
    assert cuts[1] == 19.6
    assert cuts[2] == 30.4


def test_close_sentences_are_skipped_by_min_shot():
    total, n = 40.0, 4
    starts = [10.0, 10.5, 20.0, 20.2, 30.0]
    cuts = plan_cut_times(total, n, starts)
    assert cuts == sorted(cuts)
    assert all(b - a >= 2.5 for a, b in zip([0.0] + cuts, cuts))


def test_shot_lengths_sum_to_xfade_chain_total():
    total, n = 37.4, 6
    cuts = plan_cut_times(total, n, [])
    lengths = shot_lengths(total, cuts)
    assert len(lengths) == n
    assert all(x > XFADE for x in lengths)
    chained = sum(lengths) - (n - 1) * XFADE
    assert abs(chained - total) < 0.01


def test_transition_rotation_never_repeats_consecutively():
    trans = plan_transitions(6, pan0=1)
    assert len(trans) == 5
    assert all(t in TRANSITIONS for t in trans)
    assert all(a != b for a, b in zip(trans, trans[1:]))
