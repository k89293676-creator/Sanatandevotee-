"""Validate all human inputs with one harmless live call each. Prints PASS/FAIL."""
from __future__ import annotations
import os, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from src.factory.secrets_store import get_secret
from src.factory.logging_setup import setup_logging, mask_value
import httpx

log = setup_logging("validate")
results = []

def check(name, fn):
    try:
        ok = fn()
        results.append((name, "PASS" if ok else "FAIL"))
    except Exception as e:
        results.append((name, f"FAIL ({e})"))

# Cloudflare: check wrangler auth by running npx wrangler whoami? skip (manual)
results.append(("cloudflare_login", "MANUAL"))

# Supabase
def supabase():
    url = os.environ.get("SUPABASE_URL") or __import__("os").getenv("SUPABASE_URL")
    # try env from shell
    return bool(url)
results.append(("supabase_url_present", "PASS" if os.getenv("SUPABASE_URL") else "FAIL/missing-env"))

# Telegram
def tg():
    tok = get_secret("TELEGRAM_BOT_TOKEN")
    if not tok:
        return False
    r = httpx.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=20)
    return r.status_code == 200
check("telegram_bot", tg)

# Gemini
def gem():
    k = get_secret("GEMINI_API_KEY")
    if not k:
        return False
    r = httpx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
                   params={"key": k}, json={"contents":[{"parts":[{"text":"ping"}]}]}, timeout=20)
    return r.status_code == 200
check("gemini", gem)

# Pexels
def pel():
    k = get_secret("PEXELS_API_KEY")
    if not k:
        return False
    r = httpx.get("https://api.pexels.com/v1/search", headers={"Authorization": k}, params={"query":"shiva","per_page":1}, timeout=20)
    return r.status_code == 200
check("pexels", pel)

# Factory API key presence
results.append(("factory_api_key", "PASS" if get_secret("FACTORY_API_KEY") else "FAIL/missing"))

for name, status in results:
    print(f"{name}: {status}")
print("\nDone. Re-ask only FAILs.")