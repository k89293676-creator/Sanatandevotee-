import sys, json
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.verses import get_verses
from src.factory import scriptgen, tts
from src.factory.db import connect, init_db
init_db()
vs = get_verses("shiv_chalisa")
v = vs[0]
print("verse:", v["devanagari"][:60])
res = scriptgen.generate_one(v, "meaning")
print("result:", json.dumps(res, ensure_ascii=False, indent=2) if res else "FAILED")
if res:
    conn = connect()
    conn.execute(
        """INSERT INTO scripts (verse_id,format,hooks_json,hook_styles_json,narration_hi,caption_hi,caption_roman,hashtags_json,seo_keywords_json,visual_keywords_json,image_prompts_json,est_seconds,status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(verse_id,format) DO UPDATE SET
           hooks_json=excluded.hooks_json, hook_styles_json=excluded.hook_styles_json,
           narration_hi=excluded.narration_hi, caption_hi=excluded.caption_hi,
           caption_roman=excluded.caption_roman, hashtags_json=excluded.hashtags_json,
           seo_keywords_json=excluded.seo_keywords_json, visual_keywords_json=excluded.visual_keywords_json,
           image_prompts_json=excluded.image_prompts_json, est_seconds=excluded.est_seconds, status=excluded.status""",
        (res["verse_id"], res["format"], res["hooks_json"], res["hook_styles_json"],
         res["narration_hi"], res["caption_hi"], res["caption_roman"], res["hashtags_json"],
         res["seo_keywords_json"], res["visual_keywords_json"], res["image_prompts_json"],
         res["est_seconds"], res["status"]),
    )
    conn.commit()
    conn.close()
    # measure TTS duration
    speech = tts.synthesize(res["narration_hi"], "hi-IN-MadhurNeural")
    print("TTS engine:", speech.engine, "duration:", round(speech.duration, 2), "boundaries:", len(speech.boundaries))
    words = len(res["narration_hi"].split())
    print("narration words:", words)
    print("safety: passed (generated)")