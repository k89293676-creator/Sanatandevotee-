"""One-time YouTube OAuth refresh token flow (manual)."""
from __future__ import annotations
print("Run OAuth flow manually: create client in Google Cloud, then use google-auth-oauthlib.")
print("Store refresh token via: python -c \"from src.factory.secrets_store import set_secret; set_secret('YOUTUBE_REFRESH_TOKEN','...')\"")