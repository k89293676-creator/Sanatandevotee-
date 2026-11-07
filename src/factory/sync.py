"""Sync: upload to signed URL, enqueue via Factory API."""
from __future__ import annotations
import hashlib, hmac, time, json, httpx
from pathlib import Path
from .config import load_config
from .secrets_store import get_secret
from .logging_setup import setup_logging

log = setup_logging("sync")
cfg = load_config()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def factory_headers(method: str, path: str, body: bytes) -> dict:
    key = get_secret("FACTORY_API_KEY") or ""
    secret = get_secret("FACTORY_HMAC_SECRET") or ""
    ts = str(int(time.time()))
    body_hash = hashlib.sha256(body).hexdigest()
    msg = f"{method}{path}{ts}{body_hash}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return {
        "Authorization": f"Bearer {key}",
        "X-Timestamp": ts,
        "X-Signature": sig,
        "Content-Type": "application/json",
    }


def upload_file(signed_url: str, path: Path) -> bool:
    # resumable-ish: simple PUT with retry
    for attempt in range(3):
        try:
            with path.open("rb") as f:
                r = httpx.put(signed_url, content=f, timeout=300)
            if r.status_code in (200, 201, 204):
                return True
            log.warning("upload status %s", r.status_code)
        except Exception as e:
            log.warning("upload err %s", e)
        time.sleep(2 ** attempt)
    return False


def enqueue(relay_url: str, payload: dict) -> bool:
    body = json.dumps(payload).encode()
    path = "/api/factory/enqueue"
    headers = factory_headers("POST", path, body)
    url = relay_url.rstrip("/") + path
    for attempt in range(3):
        try:
            r = httpx.post(url, content=body, headers=headers, timeout=60)
            if r.status_code in (200, 201):
                return True
            log.warning("enqueue status %s %s", r.status_code, r.text[:200])
        except Exception as e:
            log.warning("enqueue err %s", e)
        time.sleep(2 ** attempt)
    return False


def get_state(relay_url: str) -> dict | None:
    path = "/api/factory/state"
    headers = factory_headers("GET", path, b"")
    url = relay_url.rstrip("/") + path
    try:
        r = httpx.get(url, headers=headers, timeout=60)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning("get_state err %s", e)
    return None


def heartbeat(relay_url: str) -> bool:
    path = "/api/factory/heartbeat"
    body = b"{}"
    headers = factory_headers("POST", path, body)
    url = relay_url.rstrip("/") + path
    try:
        r = httpx.post(url, content=body, headers=headers, timeout=30)
        return r.status_code in (200, 204)
    except Exception as e:
        log.warning("heartbeat err %s", e)
        return False