"""Telegram notifications with dedup (relay-side usually; laptop uses for daemon alerts)."""
from __future__ import annotations
import httpx
from .secrets_store import get_secret
from .logging_setup import setup_logging

log = setup_logging("notify")


def send_telegram(text: str) -> bool:
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat = get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log.warning("telegram not configured")
        return False
    try:
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat, "text": text}, timeout=20)
        return r.status_code == 200
    except Exception as e:
        log.error("telegram send failed: %s", e)
        return False