"""Light tests: public-URL verification against object-store style responses."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory import sync  # noqa: E402


class Resp:
    def __init__(self, status=200, headers=None, content=b""):
        self.status_code = status
        self.headers = headers or {}
        self.content = content


def fake_http(monkeypatch, *, head, get):
    monkeypatch.setattr(sync.httpx, "head", lambda url, timeout=60: head)
    monkeypatch.setattr(sync.httpx, "get", lambda url, headers=None, timeout=60: get)


def test_accepts_range_response_and_total_size(monkeypatch):
    fake_http(
        monkeypatch,
        head=Resp(200, {"Content-Type": "video/mp4", "Content-Length": "1000"}),
        get=Resp(206, {"Content-Range": "bytes 0-1023/1000"}),
    )
    assert sync.verify_public_url("https://cdn.test/v.mp4", 1000) is True


def test_accepts_octet_stream_content_type(monkeypatch):
    fake_http(
        monkeypatch,
        head=Resp(200, {"Content-Type": "application/octet-stream", "Content-Length": "1000"}),
        get=Resp(206, {"Content-Range": "bytes 0-1023/1000"}),
    )
    assert sync.verify_public_url("https://cdn.test/v.mp4", 1000) is True


def test_rejects_size_mismatch_on_head(monkeypatch):
    fake_http(
        monkeypatch,
        head=Resp(200, {"Content-Type": "video/mp4", "Content-Length": "999"}),
        get=Resp(206, {"Content-Range": "bytes 0-1023/1000"}),
    )
    assert sync.verify_public_url("https://cdn.test/v.mp4", 1000) is False


def test_rejects_server_ignoring_range_with_wrong_length(monkeypatch):
    fake_http(
        monkeypatch,
        head=Resp(200, {"Content-Type": "video/mp4"}),
        get=Resp(200, {"Content-Type": "video/mp4"}, content=b"x" * 500),
    )
    assert sync.verify_public_url("https://cdn.test/v.mp4", 1000) is False


def test_accepts_full_200_when_head_has_no_length(monkeypatch):
    fake_http(
        monkeypatch,
        head=Resp(200, {"Content-Type": "video/mp4"}),
        get=Resp(200, {"Content-Type": "video/mp4"}, content=b"x" * 1000),
    )
    assert sync.verify_public_url("https://cdn.test/v.mp4", 1000) is True


def test_rejects_unreachable_url(monkeypatch):
    fake_http(
        monkeypatch,
        head=Resp(404, {}),
        get=Resp(404, {}),
    )
    assert sync.verify_public_url("https://cdn.test/missing.mp4", 1000) is False


def test_rejects_unverifiable_size(monkeypatch):
    fake_http(
        monkeypatch,
        head=Resp(200, {"Content-Type": "video/mp4"}),
        get=Resp(206, {}),
    )
    assert sync.verify_public_url("https://cdn.test/v.mp4", 1000) is False


def test_rejects_html_content_type(monkeypatch):
    fake_http(
        monkeypatch,
        head=Resp(200, {"Content-Type": "text/html", "Content-Length": "1000"}),
        get=Resp(200, {"Content-Type": "text/html"}, content=b"x" * 1000),
    )
    assert sync.verify_public_url("https://cdn.test/v.mp4", 1000) is False
