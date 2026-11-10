"""Publish Day 1 of the Shiv Chalisa series (record of the exact metadata used).

    python scripts/youtube_post_day1.py            # upload
    python scripts/youtube_post_day1.py --comment  # also post the pinned first comment

Requires YOUTUBE_* in the OS keychain (see scripts/youtube_auth.py).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.youtube_upload import upload, post_first_comment  # noqa: E402

UUID = "4ce6cb0d-498d-43fd-b07f-483acb365f21"

TITLE = "Shiv Chalisa Day 1 | Jai Girija Pati Din Dayala | #Shorts"

DESCRIPTION = """जय गिरिजा पति दीन दयाला। सदा करत संतन प्रतिपाला॥

Jai Girija Pati Din Dayala — Sada Karat Santan Pratipala.
Meaning: Glory to Shiva, consort of Parvati, compassionate to the poor, who always protects the saintly.

Chant this line when you feel afraid or lost. Trust that compassion and protection are always with you. Har Har Mahadev 🙏

Day 1 of 43 | Shiv Chalisa line by line.
Save this reel, share it with one devotee, and follow for Day 2 tomorrow.

Comment "SHIVA" to get the free PDF + audio guide.

#Shorts #ShivChalisa #HarHarMahadev #Mahadev #Shiva #ShivBhakti #Bhakti #Devotional #HinduMantra #SanatanDharma #Kailash #Rudraksha #SpiritualIndia"""

TAGS = [
    "shiv chalisa", "shiv chalisa day 1", "jai girija pati din dayala",
    "har har mahadev", "shiv bhakti", "mahadev", "shiva", "shiv mantra",
    "devotional", "hindu mantra", "kailash", "rudraksha", "shorts",
]

COMMENT = ('🙏 Har Har Mahadev! Comment "SHIVA" and I will send the free PDF + '
           'audio guide. Save this reel and follow for Day 2 of 43.')


def main() -> int:
    video = ROOT / "media" / "renders" / f"{UUID}.mp4"
    if not video.exists():
        print("missing video:", video)
        return 1
    vid = upload(video, TITLE, DESCRIPTION, tags=TAGS)
    print("VIDEO_ID:", vid)
    if not vid:
        return 1
    print("URL: https://youtube.com/shorts/" + vid)
    if "--comment" in sys.argv:
        print("COMMENT_ID:", post_first_comment(vid, COMMENT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
