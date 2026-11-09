"""Light tests: reel jobs assemble correct render specs from DB rows (no ffmpeg, no network)."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory.jobs import _json_list, build_spec   # noqa: E402
from src.factory.tts import Speech                    # noqa: E402

SPEECH = Speech(Path("v.mp3"), 30.0, "fake", [])


def _rows(**over):
    row = {"uuid": "u-1", "hook_idx": 1, "series_day": 3, "visual_style": "himalaya_dawn",
           "format": "meaning", "render_profile": "standard", "voice": "madhur",
           "hook_style": "question", "strategy": None}
    script = {"hooks_json": json.dumps(["पहला", "दूसरा", "तीसरा"], ensure_ascii=False),
              "narration_hi": "जय शिव शंकर", "visual_keywords_json": json.dumps(["diya", "temple"]),
              "image_prompts_json": json.dumps(["a calm diya"]), "format": "meaning"}
    verse = {"devanagari": "जय शिव", "roman": "Jai Shiv"}
    row.update(over)
    return row, script, verse


def test_build_spec_uses_selected_hook_and_day():
    row, script, verse = _rows()
    spec = build_spec(row, script, verse, 42, SPEECH)
    assert spec.hook == "दूसरा"
    assert spec.badge == "शिव चालीसा | दिन 3/42"
    assert spec.cta_lines[0].startswith("कल: दिन 4/42")
    assert spec.keywords == ["diya", "temple"]
    assert spec.style == "himalaya_dawn"
    assert spec.roman is None                      # meaning format has no Roman line


def test_build_spec_roman_only_for_recital():
    row, script, verse = _rows(format="recital")
    assert build_spec(row, script, verse, 42, SPEECH).roman == "Jai Shiv"


def test_build_spec_seed_is_deterministic():
    row, script, verse = _rows()
    a = build_spec(row, script, verse, 42, SPEECH)
    b = build_spec(row, script, verse, 42, SPEECH)
    assert a.seed == b.seed
    assert build_spec(_rows(uuid="u-2")[0], script, verse, 42, SPEECH).seed != a.seed


def test_build_spec_reserve_has_no_day_number():
    row, script, verse = _rows(series_day=None)
    spec = build_spec(row, script, verse, 42, SPEECH)
    assert spec.badge == "शिव चालीसा"
    assert not any("कल:" in c for c in spec.cta_lines)


def test_json_list_is_defensive():
    assert _json_list("[1, 2]") == ["1", "2"]
    assert _json_list("not json", ["x"]) == ["x"]
    assert _json_list(None, ["y"]) == ["y"]
