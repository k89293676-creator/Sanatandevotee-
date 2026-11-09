"""Light tests: generated special-day calendar is computed, labelled and honest."""
from pathlib import Path
import json
import sys
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import special_days  # noqa: E402
from src.factory import planner  # noqa: E402


def test_tithi_and_sidereal_sun_put_shivratri_in_kumbha():
    assert special_days.tithi_for_date(date(2026, 2, 15)) == 29
    assert 300.0 <= special_days.sidereal_sun_deg(date(2026, 2, 15)) < 330.0


def test_known_festival_dates():
    assert special_days.maha_shivratri(2026) == ["2026-02-15"]
    assert special_days.maha_shivratri(2027) == ["2027-03-06"]
    assert special_days.kartik_purnima(2026) == ["2026-11-24"]


def test_build_days_labels_every_year():
    days = special_days.build_days(2026, 1)["2026"]
    assert days["_note"] == special_days.EPHEM_NOTE
    for key in ("shravan_mondays", "kartik_purnima", "pradosh_vrat", "maha_shivratri"):
        assert days[key], key


def test_fallback_is_labelled_when_ephem_is_missing(monkeypatch):
    monkeypatch.setattr(special_days, "HAS_EPHEM", False)
    year = special_days.build_days(2026, 1)["2026"]
    assert year["_note"] == special_days.FALLBACK_NOTE
    assert year["maha_shivratri"] == ["2026-02-26"]


def test_written_file_is_read_by_the_planner(tmp_path, monkeypatch):
    out = tmp_path / "data" / "special_days.json"
    assert special_days.main(["--start-year", "2026", "--years", "1", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "_note" in data["2026"]
    monkeypatch.setattr(planner, "project_root", lambda: tmp_path)
    dates = planner.special_days()
    assert "2026-02-15" in dates and "_note" not in dates
