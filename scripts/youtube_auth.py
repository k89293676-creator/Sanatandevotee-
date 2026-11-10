"""Real YouTube OAuth loopback flow.

    python scripts/youtube_auth.py            # 10 min to approve in the browser
    python scripts/youtube_auth.py --port 8099 --timeout 900

Stores refresh token / client id / client secret in the OS keychain (never printed).
Scopes cover: upload, read, and channel management + comments (youtube.force-ssl).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# force-ssl is required for channel branding, playlists and the pinned first comment.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--timeout", type=int, default=600, help="seconds to wait for consent")
    args = ap.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Install: pip install google-auth-oauthlib")
        return 1

    secret_file = ROOT / "client_secret.json"
    if not secret_file.exists():
        print("Missing client_secret.json in project root "
              "(Google Cloud Console -> Credentials -> OAuth client, Desktop app).")
        return 1

    cfg = json.loads(secret_file.read_text(encoding="utf-8"))
    block = cfg.get("installed") or cfg.get("web") or {}

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
    creds = flow.run_local_server(port=args.port, timeout_seconds=args.timeout,
                                 authorization_prompt_message=
                                 "Open this URL and approve with the Moon2 channel account:\n{url}",
                                 success_message="Authorised. You can close this tab.")

    from src.factory.secrets_store import set_secret
    if not creds.refresh_token:
        print("ERROR: no refresh_token returned. Revoke the app's access at "
              "https://myaccount.google.com/permissions and re-run.")
        return 1
    set_secret("YOUTUBE_REFRESH_TOKEN", creds.refresh_token)
    if block.get("client_id"):
        set_secret("YOUTUBE_CLIENT_ID", block["client_id"])
    if block.get("client_secret"):
        set_secret("YOUTUBE_CLIENT_SECRET", block["client_secret"])
    print("refresh token stored in keychain (not printed)")
    print("token scopes:", " ".join(creds.scopes or SCOPES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
