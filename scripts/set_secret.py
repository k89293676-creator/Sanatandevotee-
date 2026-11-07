"""Set a secret via getpass into OS keychain or wrangler secret put. Never echoes value."""
from __future__ import annotations
import getpass, sys, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KEYCHAIN_NAMES = {"PIXABAY_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "PEXELS_API_KEY",
                  "FACTORY_API_KEY", "FACTORY_HMAC_SECRET", "TELEGRAM_BOT_TOKEN",
                  "TELEGRAM_CHAT_ID", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
                  "YOUTUBE_REFRESH_TOKEN", "WHATSAPP_CHANNEL_URL", "AMAZON_ASSOCIATE_TAG",
                  "COLLAB_USERNAMES"}

WRANGLER_NAMES = {"SUPABASE_SERVICE_KEY", "SUPABASE_URL", "MAKE_KEY",
                  "META_APP_ID", "META_APP_SECRET", "IG_USER_ID", "IG_ACCESS_TOKEN",
                  "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "YOUTUBE_CLIENT_ID",
                  "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN", "FACTORY_API_KEY",
                  "FACTORY_HMAC_SECRET"}

def main():
    print("Secret names (keychain):", ", ".join(sorted(KEYCHAIN_NAMES)))
    print("Secret names (wrangler):", ", ".join(sorted(WRANGLER_NAMES)))
    name = input("Secret name: ").strip()
    val = getpass.getpass("Value (hidden): ")
    if name in KEYCHAIN_NAMES:
        from src.factory.secrets_store import set_secret
        set_secret(name, val)
        print(f"Stored {name} in OS keychain.")
    if name in WRANGLER_NAMES:
        relay = ROOT / "relay"
        p = subprocess.Popen([str(relay / "node_modules" / ".bin" / "wrangler.cmd"), "secret", "put", name],
                             stdin=subprocess.PIPE, text=True, cwd=relay)
        p.communicate(val)
        print(f"wrangler secret put {name} -> exit {p.returncode}")
    if name not in KEYCHAIN_NAMES and name not in WRANGLER_NAMES:
        print("Unknown name.")

if __name__ == "__main__":
    main()