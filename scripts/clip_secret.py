"""Copy a keychain secret to clipboard without printing; clear after 60s."""
from __future__ import annotations
import sys, time, ctypes
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.secrets_store import get_secret

def set_clipboard(text: str):
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard(0)
    user32.EmptyClipboard()
    data = text.encode("utf-16-le") + b"\x00\x00"
    h = kernel32.GlobalAlloc(0x0042, len(data))
    ptr = kernel32.GlobalLock(h)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(h)
    user32.SetClipboardData(CF_UNICODETEXT, h)
    user32.CloseClipboard()

def main():
    if len(sys.argv) < 2:
        print("usage: clip_secret.py NAME")
        sys.exit(1)
    name = sys.argv[1]
    val = get_secret(name)
    if not val:
        print("not found")
        sys.exit(1)
    set_clipboard(val)
    print(f"{name} copied; clipboard will be cleared in 60s")
    time.sleep(60)
    try:
        user32 = ctypes.windll.user32
        user32.OpenClipboard(0)
        user32.EmptyClipboard()
        user32.CloseClipboard()
    except Exception:
        pass
    print("clipboard cleared")

if __name__ == "__main__":
    main()