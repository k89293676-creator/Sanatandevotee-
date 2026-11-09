"""Light tests: shot gathering never repeats an asset id (regression: 4/8 shots were one Pixabay id)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory import render                                     # noqa: E402
from src.factory.render import RenderSpec, gather_shots            # noqa: E402
from src.factory.tts import Speech                                 # noqa: E402
from src.factory.visuals.providers.base import Asset               # noqa: E402
from src.factory.visuals.strategies.base import Shot, Timeline     # noqa: E402


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


def test_strategy_timeline_decides_procedural_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "make_still",
                        lambda dest, style, seed=0: (dest.write_bytes(b"\x00"), dest)[1])

    def boom(*a, **k):
        raise AssertionError("stock fetch must not run for a procedural strategy")

    monkeypatch.setattr("src.factory.visuals.chain.fetch_asset", boom)
    timeline = Timeline(shots=[Shot(i=i, source="procedural", duration=4.0, motion="pan", overlay="caption")
                               for i in range(4)], strategy="kinetic_typography")
    shots = gather_shots(_spec(), tmp_path, 4, timeline=timeline)
    assert len(shots) == 4
    assert all(s["provider"] == "procedural" and s["kind"] == "image" for s in shots)


def test_perceptual_hash_rejects_a_reposted_stock_image(tmp_path, monkeypatch):
    from PIL import Image, ImageDraw
    import src.factory.visuals.chain as chain

    def image(dest: Path, stripes: bool) -> None:
        im = Image.new("RGB", (90, 160), "black")
        d = ImageDraw.Draw(im)
        if stripes:
            for x in range(0, 90, 10):
                d.rectangle([x, 0, x + 5, 160], fill="white")
        else:
            d.rectangle([5, 5, 85, 155], fill="white")
        im.save(dest)

    same = tmp_path / "one.jpg"
    image(same, stripes=True)
    payload = same.read_bytes()

    def fetch(kw, orientation, kind, dest, seed=0, exclude_ids=None):
        if kind != "image":
            return None
        for aid in ("id1", "id2", "id3"):
            if aid in (exclude_ids or set()):
                continue
            if aid == "id3":
                image(dest, stripes=False)
            else:
                dest.write_bytes(payload)          # same picture, new asset id
            return Asset("pixabay", aid, "u", "s", "up", "cc0", kind)
        return None

    monkeypatch.setattr(chain, "fetch_asset", fetch)
    shots = gather_shots(_spec(), tmp_path, 2)
    assert shots[0]["asset_id"] == "id1"
    assert shots[1]["asset_id"] == "id3"          # id2 was a perceptual duplicate
    assert not shots[1].get("duplicate")
