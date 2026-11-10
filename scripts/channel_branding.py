"""Generate YouTube channel artwork (banner + avatar) as PNGs, no network needed.

Text shaping for Devanagari needs HarfBuzz, which Pillow here lacks (raqm=False),
so the layout is HTML/CSS and the raster is produced by headless Chrome.

    python scripts/channel_branding.py

Outputs:
    media/branding/banner.png   2560x1440 (safe area 1546x423 centred)
    media/branding/avatar.png    800x800  (circle-cropped by YouTube)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "media" / "branding"

NAME_DEV = "शिव चालीसा ४३"
NAME_EN = "SHIV CHALISA 43"
EYEBROW = "॥ ॐ नमः शिवाय ॥"
TAGLINE = "43 दिन · 43 पंक्तियाँ · हर हर महादेव"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

BASE_CSS = """
  html, body { margin: 0; padding: 0; background: #060a1c; }
  * { -webkit-font-smoothing: antialiased; }
  .dev { font-family: 'Nirmala UI', 'Noto Sans Devanagari', 'Mangal', sans-serif; }
  .lat { font-family: 'Segoe UI', 'Inter', Arial, sans-serif; }
"""

BANNER = """<!doctype html><html><head><meta charset="utf-8"><style>
{css}
  .wrap {{ position: relative; width: 2560px; height: 1440px; overflow: hidden;
          background:
            radial-gradient(1200px 900px at 50% 46%, #2a3a72 0%, #16214a 45%, #060a1c 100%); }}
  .halo {{ position: absolute; left: 50%; top: 46%; width: 1700px; height: 1700px;
          transform: translate(-50%, -50%);
          background: radial-gradient(circle, rgba(232,180,74,0.16) 0%, rgba(232,180,74,0.05) 38%, rgba(0,0,0,0) 62%); }}
  .ring {{ position: absolute; left: 50%; top: 46%; transform: translate(-50%, -50%);
          border-radius: 50%; border: 1px solid rgba(180,200,255,0.16); }}
  .om {{ position: absolute; left: 50%; top: 46%; transform: translate(-50%, -52%);
        font-size: 760px; line-height: 1; color: rgba(180,200,255,0.07);
        text-align: center; }}
  /* YouTube safe area: 1546x423 centred, everything readable lives here. */
  .safe {{ position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
          width: 1546px; height: 423px; display: flex; flex-direction: column;
          align-items: center; justify-content: center; text-align: center; }}
  .eyebrow {{ font-size: 40px; letter-spacing: 2px; color: #b4c8ff; opacity: .92; margin-bottom: 14px; }}
  .title {{ font-size: 116px; font-weight: 700; line-height: 1.1; color: #fff5e1;
           text-shadow: 0 6px 30px rgba(0,0,0,.55); }}
  .rule {{ display: flex; align-items: center; gap: 22px; margin: 16px 0 14px; }}
  .rule i {{ display: block; width: 168px; height: 2px;
            background: linear-gradient(90deg, rgba(232,180,74,0), #e8b44a); }}
  .rule i:last-child {{ background: linear-gradient(90deg, #e8b44a, rgba(232,180,74,0)); }}
  .diamond {{ width: 12px; height: 12px; background: #e8b44a; transform: rotate(45deg); }}
  .sub {{ font-size: 34px; letter-spacing: 12px; color: #e8b44a; font-weight: 600; }}
  .tag {{ font-size: 34px; color: #d7e0ff; margin-top: 18px; opacity: .95; }}
</style></head><body><div class="wrap">
  <div class="halo"></div>
  <div class="ring" style="width:1180px;height:1180px;"></div>
  <div class="ring" style="width:1520px;height:1520px;"></div>
  <div class="om dev">ॐ</div>
  <div class="safe">
    <div class="eyebrow dev">{eyebrow}</div>
    <div class="title dev">{name_dev}</div>
    <div class="rule"><i></i><span class="diamond"></span><i></i></div>
    <div class="sub lat">{name_en}</div>
    <div class="tag dev">{tagline}</div>
  </div>
</div></body></html>
"""

AVATAR = """<!doctype html><html><head><meta charset="utf-8"><style>
{css}
  .wrap {{ width: 800px; height: 800px; position: relative;
          background: radial-gradient(420px 420px at 50% 44%, #33447f 0%, #16214a 55%, #060a1c 100%); }}
  .ring {{ position: absolute; inset: 34px; border-radius: 50%; border: 10px solid #e8b44a; }}
  .ring2 {{ position: absolute; inset: 62px; border-radius: 50%; border: 2px solid rgba(180,200,255,0.35); }}
  .om {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
        font-size: 420px; line-height: 1; color: #fff5e1; text-shadow: 0 8px 40px rgba(0,0,0,.5);
        padding-bottom: 26px; }}
  .mark {{ position: absolute; left: 0; right: 0; bottom: 128px; text-align: center;
          font-size: 52px; letter-spacing: 8px; color: #e8b44a; font-weight: 700; }}
</style></head><body><div class="wrap">
  <div class="ring"></div><div class="ring2"></div>
  <div class="om dev">ॐ</div>
  <div class="mark lat">43</div>
</div></body></html>
"""


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    return shutil.which("chrome") or shutil.which("msedge")


def render(chrome: str, html: Path, png: Path, w: int, h: int) -> None:
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=1", "--allow-file-access-from-files",
         f"--window-size={w},{h}", f"--screenshot={png}", html.as_uri()],
        check=True, capture_output=True, timeout=120,
    )


def main() -> int:
    chrome = find_chrome()
    if not chrome:
        print("no Chrome/Edge found for HTML rasterisation")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    banner_html = OUT / "banner.html"
    avatar_html = OUT / "avatar.html"
    banner_html.write_text(BANNER.format(css=BASE_CSS, eyebrow=EYEBROW, name_dev=NAME_DEV,
                                         name_en=NAME_EN, tagline=TAGLINE), encoding="utf-8")
    avatar_html.write_text(AVATAR.format(css=BASE_CSS), encoding="utf-8")

    render(chrome, banner_html, OUT / "banner.png", 2560, 1440)
    render(chrome, avatar_html, OUT / "avatar.png", 800, 800)
    print("banner:", OUT / "banner.png")
    print("avatar:", OUT / "avatar.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
