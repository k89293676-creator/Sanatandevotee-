"""Light tests: the batch renderer's guard and row loop (no ffmpeg, no TTS)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import render_batch  # noqa: E402


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.sql = []

    def execute(self, sql, params=()):
        self.sql.append(sql)
        return self

    def fetchall(self):
        return self.rows


def test_refuses_without_allow_heavy(monkeypatch, capsys):
    monkeypatch.delenv("ALLOW_HEAVY", raising=False)
    assert render_batch.main([]) == 2
    assert "ALLOW_HEAVY=1" in capsys.readouterr().out


def test_upload_without_relay_url_is_rejected(monkeypatch, capsys):
    monkeypatch.setenv("ALLOW_HEAVY", "1")
    monkeypatch.delenv("RELAY_URL", raising=False)
    assert render_batch.main(["--upload"]) == 2
    assert "--relay-url" in capsys.readouterr().out


def test_pending_rows_orders_and_limits(monkeypatch):
    conn = FakeConn([])
    render_batch.pending_rows(conn, limit=3)
    sql = conn.sql[0]
    assert "status='planned'" in sql
    assert "ORDER BY scheduled_at_utc" in sql
    assert sql.endswith("LIMIT 3")


def test_render_rows_continues_after_one_failure(monkeypatch):
    rows = [{"uuid": "a"}, {"uuid": "b"}, {"uuid": "c"}]
    calls = []
    failures = []

    def fake_render(row, conn=None):
        calls.append(row["uuid"])
        if row["uuid"] == "b":
            raise RuntimeError("boom")
        return {"mp4": f"{row['uuid']}.mp4"}

    monkeypatch.setattr(render_batch.jobs, "render_reel_row", fake_render)
    monkeypatch.setattr(render_batch.jobs, "mark_failed", lambda row, err, conn=None: failures.append((row["uuid"], err)))

    done, failed = render_batch.render_rows(rows)

    assert calls == ["a", "b", "c"]
    assert [r["uuid"] for r, _ in done] == ["a", "c"]
    assert failures == [("b", "boom")]
    assert [r["uuid"] for r, _ in failed] == ["b"]
