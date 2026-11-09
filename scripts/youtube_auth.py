"""Real YouTube OAuth loopback flow."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
    secret_file = ROOT / "client_secret.json"
    if not secret_file.exists():
        print("Missing client_secret.json in project root. Create OAuth client in Google Cloud Console.")
        sys.exit(1)
    flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
    creds = flow.run_local_server(port=8080)
    from src.factory.secrets_store import set_secret
    set_secret("YOUTUBE_REFRESH_TOKEN", creds.refresh_token)
    set_secret("YOUTUBE_CLIENT_ID", creds.client_id if hasattr(creds, "client_id") else "")
    set_secret("YOUTUBE_CLIENT_SECRET", creds.client_secret if hasattr(creds, "client_secret") else "")
    print("refresh token stored in keychain (not printed)")
except ImportError:
    print("Install: pip install google-auth-oauthlib")
except Exception as e:
    print("error:", type(e).__name__)