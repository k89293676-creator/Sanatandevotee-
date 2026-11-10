"""Light tests: local published-ledger + analytics snapshot (no network)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory import analytics  # noqa: E402


def test_add_to_ledger_appends_then_updates_in_place(tmp_path, monkeypatch):
    monkeypatch.setattr(analytics, "LEDGER_PATH", tmp_path / "ledger.json")
    assert analytics.add_to_ledger(
        {"reel_id": "r1", "youtube_video_id": "vid1", "series_day": 1}
    )
    rows = analytics.load_ledger()
    assert len(rows) == 1
    assert rows[0]["youtube_video_id"] == "vid1"

    # same video id must update the existing row, not duplicate it
    analytics.add_to_ledger(
        {"reel_id": "other", "youtube_video_id": "vid1", "series_day": 2}
    )
    rows = analytics.load_ledger()
    assert len(rows) == 1
    assert rows[0]["series_day"] == 2


def test_refresh_ledger_stats_persists_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(analytics, "LEDGER_PATH", tmp_path / "ledger.json")
    analytics.save_ledger([{"reel_id": "r1", "youtube_video_id": "vid1"}])
    monkeypatch.setattr(
        analytics,
        "youtube_stats",
        lambda vid: {"viewCount": "10", "likeCount": "2", "commentCount": "0"},
    )
    rows = analytics.refresh_ledger_stats()
    assert rows[0]["stats"]["viewCount"] == "10"
    assert "fetched_at" in rows[0]
    # persisted to disk
    assert analytics.load_ledger()[0]["stats"]["viewCount"] == "10"


def test_push_analytics_totals_and_push_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(analytics, "LEDGER_PATH", tmp_path / "ledger.json")
    analytics.save_ledger(
        [
            {"reel_id": "r1", "youtube_video_id": "v1"},
            {"reel_id": "r2", "youtube_video_id": "v2"},
        ]
    )
    stats = {
        "v1": {"viewCount": 100, "likeCount": 5, "commentCount": 1},
        "v2": {"viewCount": 50, "likeCount": 2, "commentCount": 0},
    }
    monkeypatch.setattr(analytics, "youtube_stats", lambda vid: stats[vid])

    pushed = {}
    from src.factory import jobs

    monkeypatch.setattr(
        jobs, "push_state", lambda relay, payload: pushed.update(payload) or True
    )

    snap = analytics.push_analytics("https://relay.example")
    assert snap["totals"] == {"views": 150, "likes": 7, "comments": 1}
    assert pushed["analytics_snapshot"]["totals"]["views"] == 150
    assert len(pushed["published_ledger"]) == 2
