"""Light tests: sync checker parses ASS correctly and computes real offsets."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_sync  # noqa: E402

ASS = """[Script Info]
WrapStyle: 2
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.20,0:00:01.90,Cap,,0,0,0,,जय शिव
Dialogue: 1,0:00:00.00,0:00:20.00,Badge,,0,0,0,,शिव चालीसा
Dialogue: 0,0:00:02.10,0:00:03.90,Cap,,0,0,0,,हर हर महादेव, जय
Dialogue: 3,0:00:16.80,0:00:20.00,Cta,,0,0,0,,कल मिलेंगे
"""


def test_parse_ass_returns_only_cap_cues(tmp_path):
    p = tmp_path / "c.ass"
    p.write_text(ASS, encoding="utf-8")
    cues = check_sync.parse_ass(p)
    assert [c["text"] for c in cues] == ["जय शिव", "हर हर महादेव, जय"]
    assert cues[0]["start"] == 0.2 and cues[1]["start"] == 2.1


def test_pair_offsets_is_signed_distance_to_nearest_onset():
    offs = check_sync.pair_offsets([0.2, 2.1, 4.0], [0.0, 2.0, 4.3])
    assert offs == [0.2, 0.1, -0.3]


def test_pair_offsets_without_onsets():
    assert check_sync.pair_offsets([0.2], []) == []


def test_median():
    assert check_sync._median([0.3, 0.1, 0.2]) == 0.2
    assert check_sync._median([0.1, 0.2, 0.3, 0.4]) == 0.25
