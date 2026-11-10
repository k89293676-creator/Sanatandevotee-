"""Light tests: H2 approval plumbing and the local buffer snapshot (no network, no ffmpeg)."""
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory import jobs  # noqa: E402


class FakeConn:
    """Minimal sqlite3-like conn that records writes and echoes a status lookup."""

    def __init__(self, status_by_uuid=None):
        self.updates = []
        self.commits = 0
        self._status = status_by_uuid or {}
        self._last = None

    def execute(self, sql, params=()):
        norm = " ".join(sql.split())
        if norm.upper().startswith("SELECT STATUS FROM REELS"):
            st = self._status.get(params[0])
            self._last = {"status": st} if st else None
        else:
            self.updates.append((sql, params))
            self._last = None
        return self

    def fetchone(self):
        return self._last

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def test_submit_for_approval_uploads_and_queues(tmp_path, monkeypatch):
    mp4 = tmp_path / "r.mp4"
    mp4.write_bytes(b"x" * 10)
    monkeypatch.setattr(jobs, "_reel_video_path", lambda row: mp4)
    monkeypatch.setattr(
        jobs, "_upload_preview", lambda relay, uuid, path: ("https://cdn/v.mp4", "")
    )
    captured = {}

    def fake_post(relay, path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return (200, "ok")

    monkeypatch.setattr(jobs, "_relay_post_json", fake_post)

    conn = FakeConn()
    row = {
        "uuid": "u1",
        "series_day": 2,
        "format": "meaning",
        "verse_id": 2,
        "scheduled_at_utc": "2026-11-10T01:00:00+00:00",
        "duration_s": 21.5,
    }
    script = {"caption_hi": "cap", "narration_hi": "narration text", "hashtags_json": "[]"}

    ok = jobs.submit_for_approval(row, script, "https://relay.example", conn=conn)
    assert ok
    assert captured["path"] == "/api/factory/pending-approval"
    item = captured["payload"]["items"][0]
    assert item["reel_id"] == "u1"
    assert item["video_url"] == "https://cdn/v.mp4"
    assert item["script_preview"].startswith("narration")
    # local row must be flipped to pending_approval
    assert any("status=?" in sql for sql, _ in conn.updates)
    _, params = conn.updates[-1]
    assert "pending_approval" in params


def test_submit_for_approval_does_not_mark_on_relay_failure(tmp_path, monkeypatch):
    mp4 = tmp_path / "r.mp4"
    mp4.write_bytes(b"x")
    monkeypatch.setattr(jobs, "_reel_video_path", lambda row: mp4)
    monkeypatch.setattr(
        jobs, "_upload_preview", lambda relay, uuid, path: ("https://cdn/v.mp4", "")
    )
    monkeypatch.setattr(jobs, "_relay_post_json", lambda relay, path, payload: (500, "boom"))

    conn = FakeConn()
    ok = jobs.submit_for_approval(
        {"uuid": "u1", "format": "meaning"}, {"narration_hi": "n"}, "https://relay", conn=conn
    )
    assert not ok
    assert not conn.updates  # no local status write when the relay rejects it


def test_sync_approved_flips_only_pending(monkeypatch):
    class Resp:
        status_code = 200

        def json(self):
            return {"approved": ["u1", "u2"]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())

    conn = FakeConn(status_by_uuid={"u1": "pending_approval", "u2": "rendered"})
    n = jobs.sync_approved_reels("https://relay.example", conn=conn)
    assert n == 1
    assert len(conn.updates) == 1
    _, params = conn.updates[0]
    assert "u1" in params and "rendered" in params


def test_buffer_snapshot_shape_and_push(monkeypatch):
    class BufConn:
        def execute(self, sql, params=()):
            self._sql = " ".join(sql.split())
            return self

        def fetchall(self):
            if "GROUP BY status" in self._sql:
                return [{"status": "rendered", "c": 6}, {"status": "planned", "c": 2}]
            return [
                {
                    "uuid": "u1",
                    "series_day": 1,
                    "format": "meaning",
                    "status": "rendered",
                    "scheduled_at_utc": None,
                    "duration_s": 30.0,
                }
            ]

        def close(self):
            pass

    pushed = {}
    monkeypatch.setattr(
        jobs, "push_state", lambda relay, payload: pushed.update(payload) or True
    )

    snap = jobs.buffer_snapshot("https://relay", floor=5, conn=BufConn())
    assert snap["rendered"] == 6
    assert snap["planned"] == 2
    assert snap["healthy"] is True
    assert snap["by_status"] == {"rendered": 6, "planned": 2}
    assert pushed["buffer_snapshot"]["rendered"] == 6
