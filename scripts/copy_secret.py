"""Copy/generate secrets between keychain and wrangler without printing values."""
from __future__ import annotations
import argparse, secrets, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.secrets_store import get_secret, set_secret

def to_wrangler(name: str, value: str):
    relay = ROOT / "relay"
    p = subprocess.Popen([str(relay / "node_modules" / ".bin" / "wrangler.cmd"), "secret", "put", name],
                         stdin=subprocess.PIPE, text=True, cwd=relay)
    p.communicate(value)
    return p.returncode

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--generate", action="store_true", help="generate a random value")
    ap.add_argument("--to", choices=["keychain", "wrangler", "both"], default="both")
    args = ap.parse_args()
    if args.generate:
        val = secrets.token_urlsafe(32)
    else:
        val = get_secret(args.name)
        if not val:
            print("source secret missing in keychain")
            sys.exit(1)
    if args.to in ("keychain", "both"):
        set_secret(args.name, val)
        print(f"{args.name}: stored in keychain")
    if args.to in ("wrangler", "both"):
        rc = to_wrangler(args.name, val)
        print(f"{args.name}: wrangler secret put exit {rc}")

if __name__ == "__main__":
    main()