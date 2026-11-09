import json, shutil, sys
from pathlib import Path
import pytest
pytestmark = pytest.mark.heavy
sys.path.insert(0, str(Path(__file__).parent))
from make_fake_voice import make

NARR = ("जय गिरिजा पति दीन दयाला। सदा करत संतन प्रतिपाला॥ "
        "इस पंक्ति में भक्त शिव जी को दीनों पर दया करने वाला कहता है। "
        "वे पार्वती जी के पति हैं और संतों की सदा रक्षा करते हैं। "
        "जब मन में डर हो या रास्ता न दिखे, तब इस पंक्ति को शांत मन से दोहराइए। "
        "भरोसा रखिए कि करुणा और सुरक्षा आपके साथ है। हर हर महादेव। कल मिलते हैं अगली पंक्ति के साथ।")
HOOK = "ये एक पंक्ति डर दूर करती है"
BADGE = "शिव चालीसा | दिन 1/43"
CTA = ["कल: दिन 2/43 | फॉलो करें", "फ्री पीडीएफ़ और ऑडियो: लिंक बायो में"]


def _speech(tmp_path, seconds):
    from src.factory.tts import Speech, probe_duration
    p = tmp_path / "voice.mp3"
    make(p, seconds)
    words = NARR.replace("।", " ").replace("॥", " ").split()
    d = probe_duration(p)
    step = (d - 0.6) / len(words)
    b = [{"text": w, "start": 0.3 + i * step, "end": 0.3 + (i + 1) * step - 0.03, "kind": "WordBoundary"} for i, w in enumerate(words)]
    return Speech(p, d, "fake", b)


def _spec(tmp_path, seconds=32, style="golden_diya", profile="standard", uuid="t1"):
    from src.factory.render import RenderSpec
    return RenderSpec(uuid=uuid, speech=_speech(tmp_path, seconds), hook=HOOK, badge=BADGE, narration=NARR, cta_lines=CTA,
                      style=style, profile=profile, seed=4)


def test_font_coverage_detects_latin_in_devanagari_font():
    from src.factory import fonts
    d = Path("assets/fonts")
    bad = fonts.check_strings({"badge": "Shiv Chalisa | Day 1/43"}, d)
    assert "badge" in bad and "S" in bad["badge"]          # the original bug: Latin letters -> boxes
    assert fonts.check_strings({"badge": BADGE, "hook": HOOK, "cta": " ".join(CTA)}, d) == {}


def test_chunking_and_timing_methods():
    from src.factory import captions as c
    ch = c.split_chunks(NARR, 5)
    assert all(1 < len(x.split()) <= 6 for x in ch)
    assert "।" not in " ".join(ch)
    prop = c.proportional_timings(ch, 30.0)
    assert abs(prop[-1]["end"] - 30.0) < 0.05
    words = NARR.replace("।", " ").replace("॥", " ").split()
    b = [{"text": w, "start": i * .4, "end": i * .4 + .38} for i, w in enumerate(words)]
    t, m = c.build_timings(NARR, 30.0, boundaries=b)
    assert m == "edge_boundary" and t[0]["start"] == 0.0 and all(x["end"] >= x["start"] for x in t)
    assert all(t[i]["end"] <= t[i + 1]["start"] + 1e-6 for i in range(len(t) - 1))
    t, m = c.build_timings(NARR, 30.0)            # no boundaries, no audio -> proportional on real length
    assert m == "proportional"


def test_full_render_and_validate(tmp_path):
    from src.factory.render import render_reel, validate, contact_sheet
    spec = _spec(tmp_path)
    man = render_reel(spec)
    out = Path(man["mp4"])
    assert out.exists()
    v = validate(out, man)
    print(json.dumps(v, indent=1, ensure_ascii=False))
    print("render_s", man["render_s"], man["stages_s"], man["timing_method"])
    contact_sheet(out, Path("media/contact_t1.png"))
    assert v["ok"], v["checks"]
    assert abs(v["dur"] - (spec.speech.duration + 1.0)) < 0.5     # real audio length, not truncated
    # scores must be derived, never the old hard-coded 100 / 80 / 0.1
    assert man["quality_score"] is not None and 0 <= man["quality_score"] <= 100
    assert (man["quality_score"], man["visual_score"], man["sync_median_s"]) != (100, 80, 0.1)
    assert man["metrics"]["components"]["coverage"] > 0.9
    assert man["metrics"]["checks_total"] == len(v["checks"])
    assert man["metrics"]["sync_source"] in ("measured", "unmeasured")
    # Phase D: cuts/lengths/transitions are explicit and the xfade chain is exact
    assert len(man["cut_times"]) == len(man["shots"]) - 1
    assert len(man["transitions"]) == len(man["shots"]) - 1
    assert man["cut_source"] in ("sentence", "mixed", "uniform")
    xf = 0.4
    chained = sum(man["shot_lengths_s"]) - (len(man["shots"]) - 1) * xf
    assert abs(chained - man["total_s"]) < 0.05
    assert len(set(man["transitions"])) >= min(2, len(man["transitions"]))


def test_validate_fails_for_the_right_reason(tmp_path):
    import subprocess
    from src.factory.render import validate
    # 14 s flat colour clip with silent audio -> must fail on duration, loudness, silence-free?, variety
    p = tmp_path / "bad.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x1a1a2e:s=1080x1920:d=14:r=30", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", "14", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(p)], capture_output=True)
    v = validate(p)
    assert not v["ok"]
    for k in ("duration_28_58", "loudness_-16_-12", "no_silence_over_3s", "scene_changes_ge_3", "not_flat_colour"):
        assert not v["checks"][k], k


def test_manifest_uses_complex_shaping_and_distinct_shots(tmp_path):
    from src.factory.render import render_reel, validate
    spec = _spec(tmp_path, seconds=30, style="himalaya_dawn", uuid="t2")
    man = render_reel(spec)
    assert man["shaping"] == "complex"
    assert len(man["shots"]) >= 4 and len({s["asset_id"] for s in man["shots"]}) == len(man["shots"])
    v = validate(Path(man["mp4"]), man)
    assert v["ok"], v["checks"]
