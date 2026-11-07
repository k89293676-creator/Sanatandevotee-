import sys, uuid, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.db import connect, init_db
from src.factory.verses import get_verses
from src.factory import tts, captions, render, audio_bed
from src.factory.config import media_dir

init_db()
conn = connect()
verses = get_verses("shiv_chalisa")
v = verses[0]
ex = conn.execute("SELECT id FROM scripts WHERE verse_id=? AND format=?", (v["id"], "meaning")).fetchone()
if not ex:
    conn.execute(
        """INSERT INTO scripts (verse_id,format,hooks_json,hook_styles_json,narration_hi,caption_hi,caption_roman,hashtags_json,seo_keywords_json,visual_keywords_json,image_prompts_json,est_seconds,status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (v["id"], "meaning", json.dumps(["Jai Shiv"]), json.dumps(["question"]),
         v["devanagari"] + " " + v["meaning_hi"],
         "Shiv Chalisa ka arth. Free PDF + audio: link in bio.",
         "Shiv Chalisa meaning. Free PDF + audio: link in bio.",
         json.dumps(["#ShivChalisa", "#HarHarMahadev"]), json.dumps(["shiv chalisa meaning"]),
         json.dumps(["temple", "diya", "river", "dawn", "mist", "stars"]),
         json.dumps(["calm temple diya"]), 30, "generated"),
    )
    conn.commit()
script = conn.execute("SELECT * FROM scripts WHERE verse_id=? AND format=?", (v["id"], "meaning")).fetchone()
uid = str(uuid.uuid4())
conn.execute(
    """INSERT INTO reels (uuid,verse_id,script_id,format,hook_idx,hook_style,voice,visual_style,slot_label,series_day,is_reserve,scheduled_at_utc,status)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (uid, v["id"], script["id"], "meaning", 0, "question", "madhur", "cosmic_blue", "06:30", 1, 0, "2026-11-08T01:00:00+00:00", "planned"),
)
conn.commit()
conn.close()

audio = tts.synthesize(script["narration_hi"], "hi-IN-MadhurNeural")
t = captions.proportional_timings(script["narration_hi"], 30.0, 5)
ass_path = media_dir() / "work" / (uid + ".ass")
ass_path.parent.mkdir(parents=True, exist_ok=True)
ass_path.write_text(captions.build_ass(t), encoding="utf-8")
bed = audio_bed.generate(30.0, seed=1)
mp4, cover = render.render_reel(uid, audio, ass_path, [], bed, 30.0, "hook", "Shiv Chalisa | Day 1/42", "cosmic_blue", "standard")
print("mp4:", mp4)
print("cover:", cover)
if mp4:
    print("validate:", render.validate(mp4))