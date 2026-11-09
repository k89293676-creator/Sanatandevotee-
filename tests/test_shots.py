"""Light tests: shot gathering never repeats an asset id (regression: 4/8 shots were one Pixabay id)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory import render                                     # noqa: E402
from src.factory.render import RenderSpec, gather_shots            # noqa: E402
from src.factory.tts import Speech                                 # noqa: E402
from src.factory.visuals.providers.base import Asset               # noqa: E402


def _spec():
    return RenderSpec(uuid="shots", speech=Speech(Path("v.mp3"), 30.0, "fake", []),
                      hook="", badge="", narration="", cta_lines=[],
                      keywords=["diya", "temple", "mist", "dawn"])


def _fake_fetch(pool, monkeypatch):
    def fetch(kw, orientation, kind, dest, seed=0, exclude_ids=None):
        for aid in pool:
            if aid in (exclude_ids or set()):
                continue
            dest.write_bytes(b"\x00")
            return Asset("pixabay", aid, "u", "s", "up", "cc0", kind)
        return None

    monkeypatch.setattr("src.factory.visuals.chain.fetch_asset", fetch)
    # procedural stills are real but slow; the fallback test only cares about ids/uniqueness
    monkeypatch.setattr(render, "make_still",
                        lambda dest, style, seed=0: (dest.write_bytes(b"\x00"), dest)[1])


def test_shots_are_distinct_when_candidates_exist(tmp_path, monkeypatch):
    _fake_fetch([f"id{i}" for i in range(8)], monkeypatch)
    shots = gather_shots(_spec(), tmp_path, 6)
    ids = [s["asset_id"] for s in shots]
    assert len(ids) == 6
    assert len(set(ids)) == 6
    assert all(s["provider"] == "pixabay" for s in shots)


def test_exhausted_provider_falls_back_to_procedural_not_duplicate(tmp_path, monkeypatch):
    _fake_fetch(["only-one"], monkeypatch)
    shots = gather_shots(_spec(), tmp_path, 4)
    ids = [s["asset_id"] for s in shots]
    assert len(set(ids)) == 4                       # procedural ids are unique
    assert shots[0]["provider"] == "pixabay"
    assert all(s["provider"] == "procedural" for s in shots[1:])


def test_no_assets_still_produces_unique_shots(tmp_path, monkeypatch):
    _fake_fetch([], monkeypatch)
    shots = gather_shots(_spec(), tmp_path, 3)
    assert all(s["provider"] == "procedural" for s in shots)
    assert len({s["asset_id"] for s in shots}) == 3
