"""Set up the Shiv Chalisa 43 YouTube channel page via the Data API.

Requires an OAuth token with `youtube.force-ssl` (see scripts/youtube_auth.py).

    python scripts/channel_setup.py --apply            # playlist + section + branding
    python scripts/channel_setup.py --apply --banner   # also upload/set banner.png
    python scripts/channel_setup.py --comment          # pinned first comment on Day 1

What the API cannot do (do these in YouTube Studio):
  * channel name      - brandingSettings.channel.title is read-only, the API echoes the old name
  * profile picture   - no endpoint exists for the channel avatar
  * About links       - not part of brandingSettings
  * handle            - Studio only

`channels.update` REPLACES the whole brandingSettings.channel object, so this script always
sends every field it manages (description, keywords, country, language, trailer). A partial
update silently wipes the fields you left out.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.youtube_upload import refresh_access_token  # noqa: E402

API = "https://www.googleapis.com/youtube/v3"
BRANDING_DIR = ROOT / "media" / "branding"

PLAYLIST_TITLE = "Shiv Chalisa 43 — पूरी श्रृंखला (Day 1–43)"
PLAYLIST_DESC = (
    "शिव चालीसा की 43 पंक्तियाँ, एक-एक दिन, क्रम से।\n"
    "हर रील में पंक्ति, उसका अर्थ और जीवन में उपयोग।\n\n"
    "Day 1 to Day 43 of Shiv Chalisa — recitation, meaning, one line a day."
)
SECTION_TITLE = "Shiv Chalisa 43 — पूरी श्रृंखला"
DAY1_VIDEO = "gJBHA7cb4H0"

DESCRIPTION_TEMPLATE = """शिव चालीसा — 43 दिन, 43 पंक्तियाँ, एक भक्ति यात्रा।

हर दिन शिव चालीसा की एक पंक्ति: पाठ, अर्थ और जीवन में उसका उपयोग। छोटे रील्स, हिंदी नैरेशन, शांत संगीत और कैलाश-हिमालय के दृश्य।

Shiv Chalisa, one line a day — recitation, meaning, and how to use it in daily life. Short Hindi reels with Himalayan and Kailash visuals.

नया रील: रोज़ सुबह 6:00 बजे (IST)
New reel daily at 6:00 AM IST

▶ पूरी श्रृंखला क्रम से / Start from Day 1:
{playlist_url}

📿 फ्री PDF + ऑडियो गाइड: किसी भी रील पर "SHIVA" कमेंट करें
📿 Free PDF + audio guide: comment "SHIVA" on any reel

हर हर महादेव 🙏
"""

KEYWORDS = ",".join([
    '"shiv chalisa"', '"shiv chalisa 43"', '"shiv chalisa day 1"',
    '"जय गिरिजा पति दीन दयाला"', '"har har mahadev"', '"shiv bhakti"',
    '"mahadev"', '"shiva"', '"shiv mantra"', '"chalisa"', '"shiv aarti"',
    '"hindi devotional"', '"devotional"', '"bhakti"', '"sanatan dharma"',
    '"kailash"', '"rudraksha"', '"spiritual"',
])

FIRST_COMMENT = (
    '🙏 Har Har Mahadev! Comment "SHIVA" and I will send the free PDF + audio guide. '
    'Save this reel and follow for Day 2 of 43.'
)


def _h(token: str, json_body: bool = True) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def scopes(token: str) -> str:
    r = httpx.get("https://oauth2.googleapis.com/tokeninfo",
                  params={"access_token": token}, timeout=30)
    return r.json().get("scope", "") if r.status_code == 200 else ""


def my_channel(token: str) -> dict:
    r = httpx.get(f"{API}/channels", params={"part": "snippet,brandingSettings", "mine": "true"},
                  headers=_h(token, False), timeout=60)
    r.raise_for_status()
    return r.json()["items"][0]


# ---------------------------------------------------------------- playlist ----
def find_playlist(token: str, title: str) -> str | None:
    r = httpx.get(f"{API}/playlists",
                  params={"part": "snippet", "mine": "true", "maxResults": "50"},
                  headers=_h(token, False), timeout=60)
    if r.status_code != 200:
        return None
    for it in r.json().get("items", []):
        if it["snippet"]["title"].strip() == title.strip():
            return it["id"]
    return None


def ensure_playlist(token: str, title: str, description: str) -> str:
    existing = find_playlist(token, title)
    if existing:
        print("playlist exists:", existing)
        return existing
    body = {"snippet": {"title": title, "description": description, "defaultLanguage": "hi"},
            "status": {"privacyStatus": "public"}}
    r = httpx.post(f"{API}/playlists", params={"part": "snippet,status"},
                   headers=_h(token), json=body, timeout=60)
    print("playlists.insert", r.status_code, "" if r.status_code < 300 else r.text[:300])
    r.raise_for_status()
    return r.json()["id"]


def add_video(token: str, playlist_id: str, video_id: str) -> None:
    body = {"snippet": {"playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
    r = httpx.post(f"{API}/playlistItems", params={"part": "snippet"},
                   headers=_h(token), json=body, timeout=60)
    print("playlistItems.insert", r.status_code, "" if r.status_code < 300 else r.text[:300])


# ----------------------------------------------------------------- section ----
def ensure_section(token: str, playlist_id: str) -> None:
    r = httpx.get(f"{API}/channelSections",
                  params={"part": "snippet,contentDetails", "mine": "true"},
                  headers=_h(token, False), timeout=60)
    for it in r.json().get("items", []) if r.status_code == 200 else []:
        if playlist_id in (it.get("contentDetails", {}).get("playlists") or []):
            print("section exists:", it["id"])
            return
    body = {"snippet": {"type": "singleplaylist", "style": "horizontalRow",
                        "title": SECTION_TITLE, "defaultLanguage": "hi"},
            "contentDetails": {"playlists": [playlist_id]}}
    r = httpx.post(f"{API}/channelSections", params={"part": "snippet,contentDetails"},
                   headers=_h(token), json=body, timeout=60)
    print("channelSections.insert", r.status_code, "" if r.status_code < 300 else r.text[:300])


# ------------------------------------------------------------ branding/banner --
def upload_banner(token: str, png: Path) -> str:
    """channelBanners.insert is occasionally 503; retry a few times before failing."""
    last = ""
    for attempt in range(3):
        init = httpx.post(
            "https://www.googleapis.com/upload/youtube/v3/channelBanners/insert",
            params={"uploadType": "media"},
            headers={**_h(token, False), "Content-Type": "image/png",
                     "X-Upload-Content-Type": "image/png"},
            content=png.read_bytes(), timeout=300.0,
        )
        print("channelBanners.insert", init.status_code,
              "" if init.status_code < 300 else init.text[:300])
        if init.status_code < 300:
            return init.json()["url"]
        last = init.text[:300]
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"banner upload failed: {last}")


def update_channel(token: str, channel_id: str, *, description: str,
                   banner_url: str | None, trailer: str = DAY1_VIDEO) -> dict:
    """One full replacement of brandingSettings.channel (never a partial PUT).

    A PUT replaces the object, so an omitted banner/description is erased. When no new
    banner is supplied we keep the one already on the channel.
    """
    if not banner_url:
        current = my_channel(token).get("brandingSettings", {})
        banner_url = (current.get("image", {}) or {}).get("bannerExternalUrl")
        if banner_url:
            print("keeping existing banner")
    channel = {
        "description": description,
        "keywords": KEYWORDS,
        "country": "IN",
        "defaultLanguage": "hi",
        "unsubscribedTrailer": trailer,
    }
    branding: dict = {"channel": channel}
    if banner_url:
        branding["image"] = {"bannerExternalUrl": banner_url}
    r = httpx.put(f"{API}/channels", params={"part": "brandingSettings"},
                  headers=_h(token), json={"id": channel_id, "brandingSettings": branding},
                  timeout=60)
    print("channels.update", r.status_code, "" if r.status_code < 300 else r.text[:600])
    r.raise_for_status()
    return r.json()


def post_comment(token: str, video_id: str, text: str) -> None:
    body = {"snippet": {"videoId": video_id,
                        "topLevelComment": {"snippet": {"textOriginal": text}}}}
    r = httpx.post(f"{API}/commentThreads", params={"part": "snippet"},
                   headers=_h(token), json=body, timeout=60)
    print("commentThreads.insert", r.status_code, "" if r.status_code < 300 else r.text[:400])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="playlist + section + branding")
    ap.add_argument("--banner", action="store_true", help="upload and set banner.png")
    ap.add_argument("--banner-url", default="",
                    help="reuse an already-uploaded channelBanners URL")
    ap.add_argument("--comment", action="store_true", help="post the pinned first comment")
    args = ap.parse_args()

    token = refresh_access_token()
    if not token:
        print("no access token (run scripts/youtube_auth.py)")
        return 1
    print("scopes:", scopes(token))
    ch = my_channel(token)
    cid = ch["id"]
    print("channel:", ch["snippet"]["title"], cid)

    playlist_url = ""
    if args.apply:
        playlist_id = ensure_playlist(token, PLAYLIST_TITLE, PLAYLIST_DESC)
        add_video(token, playlist_id, DAY1_VIDEO)
        ensure_section(token, playlist_id)
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        print("playlist url:", playlist_url)

        banner_url = args.banner_url or None
        if args.banner and not banner_url:
            banner_url = upload_banner(token, BRANDING_DIR / "banner.png")
        update_channel(token, cid, description=DESCRIPTION_TEMPLATE.format(
            playlist_url=playlist_url), banner_url=banner_url)

    if args.comment:
        post_comment(token, DAY1_VIDEO, FIRST_COMMENT)

    ch = my_channel(token)
    b = ch.get("brandingSettings", {})
    chb = b.get("channel", {}) or {}
    print(json.dumps({
        "title": ch["snippet"]["title"],
        "desc_chars": len(chb.get("description") or ""),
        "keywords": chb.get("keywords"),
        "trailer": chb.get("unsubscribedTrailer"),
        "country": chb.get("country"),
        "language": chb.get("defaultLanguage"),
        "banner": (b.get("image", {}) or {}).get("bannerExternalUrl"),
        "playlist": playlist_url,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
