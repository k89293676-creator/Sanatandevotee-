"""Light tests: the default strategy keeps stock footage in the reel; explicit
procedural strategies still plan procedural stills."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory.render import RenderSpec                        # noqa: E402
from src.factory.tts import Speech                               # noqa: E402
from src.factory.visuals.strategies import STRATEGIES, get_strategy   # noqa: E402


def _spec(**kw):
    return RenderSpec(uuid="s", speech=Speech(Path("v.mp3"), 30.0, "fake", []),
                      hook="", badge="", narration="", cta_lines=[], **kw)


def test_default_spec_keeps_stock_in_the_plan():
    spec = _spec()
    assert spec.strategy == "mixed_montage"
    timeline = get_strategy(spec.strategy).plan(spec, 4)
    assert [s.source for s in timeline.shots] == ["image", "video", "image", "video"]


def test_all_named_strategies_are_available():
    for name in STRATEGIES:
        timeline = get_strategy(name).plan(_spec(), 3)
        assert len(timeline.shots) == 3
        assert all(s.source in ("image", "video", "procedural") for s in timeline.shots)


def test_unknown_strategy_falls_back_to_stock_mix():
    timeline = get_strategy("does_not_exist").plan(_spec(), 2)
    assert timeline.strategy == "mixed_montage"
    assert [s.source for s in timeline.shots] == ["image", "video"]
