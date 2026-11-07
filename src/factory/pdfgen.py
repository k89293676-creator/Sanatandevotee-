"""Generate Shiv Chalisa PDF with Devanagari."""
from __future__ import annotations
from pathlib import Path
from .verses import get_verses
from .logging_setup import setup_logging

log = setup_logging("pdfgen")
RELAY_PUBLIC = Path(__file__).resolve().parents[2] / "relay" / "public"


def build_html() -> str:
    verses = get_verses("shiv_chalisa")
    body = ""
    for v in verses:
        body += f"<h3>{v['seq']}. {v['devanagari']}</h3>\n"
        body += f"<p class='roman'>{v['roman']}</p>\n"
        body += f"<p class='meaning'>{v['meaning_hi']}</p>\n"
        body += f"<p class='en'>{v['meaning_en']}</p>\n"
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
@font-face{{font-family:'Noto';src:url('../assets/fonts/NotoSansDevanagari-Regular.ttf')}}
body{{font-family:'Noto',serif;margin:2cm;line-height:1.6}}
h1{{text-align:center}}
h3{{margin-top:1em;color:#333}}
.roman{{color:#555;font-style:italic}}
.meaning{{color:#222}}
.en{{color:#666;font-size:0.9em}}
</style></head><body>
<h1>शिव चालीसा — अर्थ सहित</h1>
{body}
<p><small>AI-assisted visuals; recitation text traditional.</small></p>
</body></html>"""


def generate_pdf() -> Path | None:
    RELAY_PUBLIC.mkdir(parents=True, exist_ok=True)
    html_path = RELAY_PUBLIC / "chalisa.html"
    html_path.write_text(build_html(), encoding="utf-8")
    out = RELAY_PUBLIC / "chalisa.pdf"
    # try weasyprint
    try:
        import weasyprint
        weasyprint.HTML(filename=str(html_path)).write_pdf(str(out))
        if out.exists():
            return out
    except Exception as e:
        log.warning("weasyprint fail: %s", e)
    # fallback: headless chrome/edge
    for binname in ["msedge", "chrome", "chromium"]:
        exe = None
        import shutil
        exe = shutil.which(binname) or shutil.which(binname + ".exe")
        if exe:
            import subprocess
            try:
                subprocess.run([exe, "--headless", "--print-to-pdf=" + str(out), str(html_path)],
                               check=True, timeout=120)
                if out.exists():
                    return out
            except Exception as e:
                log.warning("chrome fail: %s", e)
    log.error("pdf generation failed")
    return None