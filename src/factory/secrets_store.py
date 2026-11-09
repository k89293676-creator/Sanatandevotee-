"""OS keychain access via keyring. Never store secrets in files."""
from __future__ import annotations
import keyring
from typing import Optional

SERVICE = "chalisa-factory"


def get_secret(name: str) -> Optional[str]:
    import os
    v = os.environ.get(name)
    if v:
        return v
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:
        return None


def set_secret(name: str, value: str) -> None:
    keyring.set_password(SERVICE, name, value)


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except Exception:
        pass


LAPTOP_SECRET_NAMES = [
    "GEMINI_API_KEY", "GROQ_API_KEY", "PEXELS_API_KEY",
    "FACTORY_API_KEY", "FACTORY_HMAC_SECRET",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN",
    "WHATSAPP_CHANNEL_URL", "AMAZON_ASSOCIATE_TAG", "COLLAB_USERNAMES",
]