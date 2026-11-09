"""Set secrets via getpass or clipboard into OS keychain or wrangler. Never echoes values."""
from __future__ import annotations
import argparse, getpass, re, sys, subprocess, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KEYCHAIN_NAMES = {"PIXABAY_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "PEXELS_API_KEY",
                  "FACTORY_API_KEY", "FACTORY_HMAC_SECRET", "TELEGRAM_BOT_TOKEN",
                  "TELEGRAM_CHAT_ID", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
                  "YOUTUBE_REFRESH_TOKEN", "WHATSAPP_CHANNEL_URL", "AMAZON_ASSOCIATE_TAG",
                  "COLLAB_USERNAMES", "MAKE_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"}
WRANGLER_NAMES = {"SUPABASE_SERVICE_KEY", "SUPABASE_URL", "MAKE_KEY",
                  "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "YOUTUBE_CLIENT_ID",
                  "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN", "FACTORY_API_KEY",
                  "FACTORY_HMAC_SECRET"}

def read_clipboard() -> str:
    import ctypes
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(0):
        return ""
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()

def clear_clipboard():
    try:
        import ctypes
        ctypes.windll.user32.OpenClipboard(0)
        ctypes.windll.user32.EmptyClipboard()
        ctypes.windll.user32.CloseClipboard()
    except Exception:
        pass

def validate(name: str, val: str) -> tuple[bool, str]:
    if len(val) < 20:
        return False, "too short (<20)"
    if any(ord(c) < 32 for c in val):
        return False, "control characters present"
    if name == "TELEGRAM_BOT_TOKEN":
        if not re.match(r"^\d{8,10}:[A-Za-z0-9_-]{30,}$", val):
            return False, "expected id:token pattern"
    if name == "SUPABASE_SERVICE_KEY":
        if not (val.startswith("sb_secret_") or val.startswith("eyJ")):
            return False, "expected sb_secret_ or JWT (eyJ...)"
    if name == "PIXABAY_API_KEY":
        if not re.match(r"^\d+-[0-9a-f]{16,}$", val):
            return False, "expected digits-hex pattern"
    if name == "SUPABASE_URL":
        if not val.startswith("https://"):
            return False, "expected https:// URL"
    return True, "ok"

def live_check(name: str, val: str) -> str:
    import httpx
    try:
        if name == "TELEGRAM_BOT_TOKEN":
            r = httpx.get(f"https://api.telegram.org/bot{val}/getMe", timeout=15)
            return "PASS" if r.status_code == 200 else "FAIL"
        if name == "SUPABASE_SERVICE_KEY":
            url = None
            try:
                from src.factory.secrets_store import get_secret
                url = get_secret("SUPABASE_URL")
            except Exception:
                pass
            import os
            url = url or os.getenv("SUPABASE_URL")
            if not url:
                return "SKIP(no url)"
            r = httpx.get(url.rstrip("/") + "/rest/v1/", headers={"apikey": val, "Authorization": "Bearer " + val}, timeout=15)
            return "PASS" if r.status_code in (200, 404) else "FAIL"
        if name == "GEMINI_API_KEY":
            r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": val}, timeout=15)
            return "PASS" if r.status_code == 200 else "FAIL"
        if name == "PIXABAY_API_KEY":
            r = httpx.get("https://pixabay.com/api/", params={"key": val, "q": "test", "per_page": 1}, timeout=15)
            return "PASS" if r.status_code == 200 else "FAIL"
        if name == "MAKE_KEY":
            return "SKIP(no live check)"
        return "SKIP"
    except Exception:
        return "FAIL"

def to_wrangler(name: str, value: str):
    relay = ROOT / "relay"
    p = subprocess.Popen([str(relay / "node_modules" / ".bin" / "wrangler.cmd"), "secret", "put", name],
                         stdin=subprocess.PIPE, text=True, cwd=relay)
    p.communicate(value)
    return p.returncode

def store_one(name: str, val: str, target: str) -> bool:
    ok, msg = validate(name, val)
    if not ok:
        print(f"  REJECTED {name}: {msg}")
        return False
    if target in ("keychain", "both") and name in KEYCHAIN_NAMES:
        from src.factory.secrets_store import set_secret
        set_secret(name, val)
        print(f"  {name}: keychain OK")
    if target in ("wrangler", "both") and name in WRANGLER_NAMES:
        rc = to_wrangler(name, val)
        print(f"  {name}: wrangler exit {rc}")
    print(f"  {name} live check: {live_check(name, val)}")
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="single secret name")
    ap.add_argument("--names", help="comma-separated list of names")
    ap.add_argument("--from-clipboard", action="store_true")
    ap.add_argument("--paste", action="store_true", help="read value from a pasted line on stdin")
    ap.add_argument("--target", choices=["keychain", "wrangler", "both"], default="both")
    ap.add_argument("--list", action="store_true", help="list known secret names")
    args = ap.parse_args()

    if args.list:
        print("Keychain:", ", ".join(sorted(KEYCHAIN_NAMES)))
        print("Wrangler:", ", ".join(sorted(WRANGLER_NAMES)))
        return

    names = []
    if args.names:
        names = [n.strip() for n in args.names.split(",") if n.strip()]
    elif args.name:
        names = [args.name]
    else:
        print("Provide --name or --names")
        sys.exit(1)

    for name in names:
        print(f"--- {name} ---")
        if args.from_clipboard:
            val = read_clipboard()
            if not val:
                print("  clipboard empty")
                sys.exit(1)
        elif args.paste:
            print(f"  Paste value for {name} then press Enter:")
            val = sys.stdin.readline().rstrip("\r\n")
        else:
            val = getpass.getpass(f"  Value for {name} (hidden): ")
        ok = store_one(name, val, args.target)
        # clear clipboard only after success
        if args.from_clipboard and ok:
            clear_clipboard()
        if not ok:
            sys.exit(1)
        # pause between multiple clipboard reads
        if args.from_clipboard and len(names) > 1:
            print("  Copy next value to clipboard, then press Enter...")
            input()

if __name__ == "__main__":
    main()