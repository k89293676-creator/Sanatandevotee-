import sys, uuid, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.db import connect, init_db
from src.factory.verses import get_verses
from src.factory import tts, captions, render, fonts
from src.factory.config import media_dir, load_config

init_db()
conn = connect()
verses = get_verses("shiv_chalisa")
v = verses[0]
script_row = conn.execute("SELECT * FROM scripts WHERE verse_id=? AND format=?", (v["id"], "meaning")).fetchone()
narr = script_row["narration_hi"] if script_row else ((v["devanagari"] + " ") * 4 + (v["meaning_hi"] + " ") * 3)
uid = str(uuid.uuid4())

# ensure script row
ex = conn.execute("SELECT id FROM scripts WHERE verse_id=? AND format=?", (v["id"], "meaning")).fetchone()
if not ex:
    conn.execute(
        """INSERT INTO scripts (verse_id,format,hooks_json,hook_styles_json,narration_hi,caption_hi,caption_roman,hashtags_json,seo_keywords_json,visual_keywords_json,image_prompts_json,est_seconds,status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (v["id"], "meaning", json.dumps(["Jai Shiv"]), json.dumps(["question"]),
         narr,
         "Shiv Chalisa ka arth. Free PDF + audio: link in bio.",
         "Shiv Chalisa meaning. Free PDF + audio: link in bio.",
         json.dumps(["#ShivChalisa", "#HarHarMahadev"]), json.dumps(["shiv chalisa meaning"]),
         json.dumps(["temple", "diya", "river", "dawn", "mist", "stars"]),
         json.dumps(["calm temple diya"]), 40, "generated"),
    )
    conn.commit()
script = conn.execute("SELECT * FROM scripts WHERE verse_id=? AND format=?", (v["id"], "meaning")).fetchone()
conn.close()

speech = tts.synthesize(narr, "hi-IN-MadhurNeural")
print("tts engine:", speech.engine, "duration:", speech.duration, "boundaries:", len(speech.boundaries))

N = 42
spec = render.RenderSpec(
    uuid=uid,
    speech=speech,
    hook="जय शिव शंकर",
    badge="शिव चालीसा | दिन 1/%d" % N,
    narration=narr,
    cta_lines=["कल: दिन 2/%d" % N, "फ्री पीडीएफ + ऑडियो: लिंक इन बायो"],
    style="golden_diya",
    profile="standard",
    keywords=["diya", "temple", "mist", "dawn", "river"],
    image_prompts=["calm temple diya flame", "himalaya mist dawn"],
    seed=1,
)
manifest = render.render_reel(spec)
print("mp4:", manifest["mp4"])
print("cover:", manifest["cover"])
print("total_s:", manifest["total_s"], "audio_s:", manifest["audio_s"], "timing:", manifest["timing_method"])
print("stages:", manifest["stages_s"])
mp4p = Path(manifest["mp4"])
print("validate:", render.validate(mp4p, manifest))
cs = render.contact_sheet(mp4p, media_dir() / "work" / (uid + "_sheet.jpg"))
print("contact_sheet:", cs)