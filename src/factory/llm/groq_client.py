"""Groq LLM client (OpenAI-compatible)."""
from __future__ import annotations
import httpx, json, hashlib, time
from pathlib import Path
from typing import Optional
from ..secrets_store import get_secret
from ..logging_setup import setup_logging

log = setup_logging("groq_client")
BASE = "https://api.groq.com/openai/v1"


def _key() -> str | None:
    return get_secret("GROQ_API_KEY")


def chat(model: str, messages: list, temperature: float = 0.7, json_mode: bool = True,
         timeout: float = 90.0) -> dict | None:
    key = _key()
    if not key:
        return None
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        r = httpx.post(f"{BASE}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                       json=payload, timeout=httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=10.0))
        if r.status_code == 429:
            ra = r.headers.get("retry-after")
            log.warning("groq 429 retry-after=%s", ra)
            return None
        if r.status_code in (404, 400) and "model" in r.text.lower():
            log.warning("groq model-not-found: %s", model)
            return None
        if r.status_code != 200:
            log.warning("groq %s: %s", r.status_code, r.text[:200])
            return None
        return r.json()
    except Exception as e:
        log.warning("groq err: %s", e)
        return None


def list_models() -> list[str]:
    key = _key()
    if not key:
        return []
    try:
        r = httpx.get(f"{BASE}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        if r.status_code == 200:
            return [m["id"] for m in r.json().get("data", [])]
    except Exception as e:
        log.warning("groq list_models err: %s", e)
    return []


def extract_content(resp: dict) -> str | None:
    try:
        return resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None