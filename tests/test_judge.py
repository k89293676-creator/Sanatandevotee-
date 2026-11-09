"""Light tests: the judge measures text (no constants) and scores are persisted."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory.content_engine import judge          # noqa: E402
from src.factory.db import connect, init_db           # noqa: E402
from src.factory.script_store import save_script, score_for   # noqa: E402

VERSE = {"devanagari": "जय गिरिजा पति दीन दयाला।", "meaning_hi": "भक्त शिव जी को दीनों पर दया करने वाला कहता है।"}

SENTENCES = [
    "जय गिरिजा पति दीन दयाला सदा करत संतन प्रतिपाला",
    "यह पंक्ति भक्त की रक्षा और करुणा का भाव बताती है",
    "जब मन में डर हो तब इसे शांत मन से दोहराइए",
    "भरोसा रखिए कि करुणा सदा आपके साथ है",
    "शिव जी दीनों पर दया करते हैं ऐसा भक्त कहता है",
    "इस पंक्ति में समर्पण और विश्वास की शिक्षा मिलती है",
    "हर हर महादेव कल मिलते हैं अगली पंक्ति के साथ",
    "शांत मन से जप करने पर भीतर स्थिरता आती है",
]


def _good() -> dict:
    return {
        "hooks": ["ये पंक्ति डर दूर करती है", "क्या आप जानते हैं यह राज", "एक पंक्ति जो रक्षा करती है",
                  "भय से साहस तक का रास्ता", "तीन सेकंड में शांति"],
        "hook_styles": ["fear_to_courage", "curiosity", "benefit", "story_tease", "question"],
        "narration_hi": " ".join(SENTENCES),
        "caption_hi": "शिव चालीसा का अर्थ। फ्री पीडीएफ लिंक इन बायो।",
        "caption_roman": "Shiv Chalisa meaning. Free PDF in bio.",
        "hashtags": ["#ShivChalisa", "#HarHarMahadev", "#Bhakti", "#Shiv"],
        "seo_keywords": ["shiv chalisa", "chalisa arth", "shiv bhakti"],
        "visual_keywords": ["diya", "temple", "mist", "trishul", "incense", "himalaya"],
        "image_prompts": ["calm diya", "misty temple", "himalaya dawn"],
        "est_seconds": 35,
    }


def test_judge_scores_good_script_high():
    sc = judge(_good(), VERSE)
    assert sc["pass"], sc["reasons"]
    assert sc["total"] >= 85
    assert sc["hard_gates"] == {"safety": True, "verse_intact": True, "no_banned_opener": True}
    assert sc["judge_model"] == "rules-v1"


def test_judge_rejects_latin_and_missing_verse():
    bad = {"narration_hi": "Today we chant *mantra* for peace", "hooks": [], "hashtags": [],
           "caption_hi": "", "est_seconds": 10}
    sc = judge(bad, VERSE)
    assert not sc["pass"]
    assert sc["hard_gates"]["verse_intact"] is False
    assert any("verse text missing" in r for r in sc["reasons"])
    assert any("devanagari" in r for r in sc["reasons"])
    assert sc["total"] < 40


def test_judge_flags_banned_opener_and_cure_claims():
    s = _good()
    s["narration_hi"] = "नमस्कार " + s["narration_hi"] + " यह गारंटी है"
    sc = judge(s, VERSE)
    assert sc["hard_gates"]["no_banned_opener"] is False
    assert sc["hard_gates"]["safety"] is False
    assert not sc["pass"]


def _db(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    return connect(p)


def test_save_script_persists_script_and_score(tmp_path):
    conn = _db(tmp_path)
    vid = conn.execute(
        "INSERT INTO verses (pack,seq,kind,devanagari,roman,meaning_hi,meaning_en,verified_flag)"
        " VALUES ('p',1,'doha',?,?,?,?,0)",
        (VERSE["devanagari"], "jai girija", VERSE["meaning_hi"], "meaning"),
    ).lastrowid
    script = _good()
    script["score"] = judge(script, VERSE)
    sid = save_script({"id": vid}, "meaning", script, conn=conn)

    assert conn.execute("SELECT COUNT(*) c FROM scripts").fetchone()["c"] == 1
    row = score_for(sid, conn=conn)
    assert row and row["total"] == script["score"]["total"]
    assert row["judge_model"] == "rules-v1"
    # resuming must not duplicate
    assert save_script({"id": vid}, "meaning", script, conn=conn) == sid
    assert conn.execute("SELECT COUNT(*) c FROM scripts").fetchone()["c"] == 1
    conn.close()
