"""Light tests: the H1 text-review reporter classifies matches without touching gates."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import verify_text  # noqa: E402


SOURCE = (
    "जय शिव। हर हर महादेव जय। "
    "जय शिव चालीसा कुछ और शब्द यहाँ हैं। "
    "नमस्ते दुनिया।"
)


def test_normalize_strips_danda_and_punctuation():
    assert verify_text.normalize("जय शिव। हर, हर!") == ["जय", "शिव", "हर", "हर"]


def test_locate_uses_first_three_words_as_anchor():
    words = verify_text.normalize(SOURCE)
    start, end = verify_text.locate(words, "हर हर महादेव जय")
    assert words[start:end] == ["हर", "हर", "महादेव"]


def test_locate_returns_negative_when_absent():
    assert verify_text.locate(verify_text.normalize(SOURCE), "कुछ भी नहीं") == (-1, -1)


def test_compare_unit_exact_text_is_match():
    res = verify_text.compare_unit("जय शिव", SOURCE)
    assert res["status"] == "MATCH"
    assert res["ratio"] >= 0.97


def test_compare_unit_small_change_is_minor_diff():
    # one token differs in a ten-token unit: ratio = 2*9/(10+10)
    res = verify_text.compare_unit(
        "जय शिव चालीसा पाठ करो हर दिन शिव की जय",
        "जय शिव चालीसा पाठ करो हर दिन शिव और जय नमस्ते दुनिया",
        next_text="नमस्ते दुनिया",
    )
    assert res["status"] == "MINOR_DIFF"
    assert 0.85 <= res["ratio"] < 0.97


def test_compare_unit_unrelated_tail_is_diff():
    res = verify_text.compare_unit(
        "जय शिव चालीसा पाठ",
        "जय शिव चालीसा एक दो तीन चार पाँच छह",
        next_text="दो तीन चार",
    )
    assert res["status"] == "DIFF"


def test_compare_unit_missing_text():
    res = verify_text.compare_unit("कुछ भी नहीं है", SOURCE)
    assert res["status"] == "MISSING"
    assert res["ratio"] == 0.0


def test_build_review_covers_every_source_for_every_unit():
    units = [{"seq": 1, "devanagari": "जय शिव"}, {"seq": 2, "devanagari": "कुछ भी नहीं है"}]
    rows = verify_text.build_review(units, {"a": SOURCE, "b": SOURCE})
    assert [r["seq"] for r in rows] == [1, 2]
    assert set(rows[0]["sources"]) == {"a", "b"}
    assert rows[0]["sources"]["a"]["status"] == "MATCH"
    assert rows[1]["sources"]["b"]["status"] == "MISSING"


def test_write_markdown_records_discrepancies_and_h1_note(tmp_path, monkeypatch):
    out = tmp_path / "TEXT_REVIEW.md"
    monkeypatch.setattr(verify_text, "OUT", out)
    units = [{"seq": 1, "devanagari": "जय शिव"}, {"seq": 2, "devanagari": "कुछ भी नहीं है"}]
    sources = {"source_a": SOURCE}
    rows = verify_text.build_review(units, sources)
    verify_text.write_markdown(rows, sources)
    text = out.read_text(encoding="utf-8")

    assert "does not change `verified_flag`" in text
    assert "| 1 | MATCH" in text
    assert "MISSING" in text
    assert "## Discrepancies" in text


def test_main_without_sources_exits_2(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["verify_text.py"])
    assert verify_text.main() == 2


def test_reporter_never_flips_the_h1_gate():
    """Guard: H1 is human-only, so the reporter must not contain a write path."""
    source = Path(verify_text.__file__).read_text(encoding="utf-8").replace(" ", "")
    assert "verified_flag=1" not in source
    assert "verified_flag=true" not in source.lower()
