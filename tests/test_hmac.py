import sys, hashlib, hmac, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.sync import factory_headers

def test_headers_present():
    # Without secrets in keychain, factory_headers still returns structure
    h = factory_headers("GET", "/api/factory/state", b"")
    assert "X-Signature" in h
    assert "X-Timestamp" in h