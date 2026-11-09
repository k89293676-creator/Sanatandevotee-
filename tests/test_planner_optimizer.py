"""Light tests: calendar data is actually read and the optimizer floor is honoured."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factory import optimizer, planner   # noqa: E402


def test_special_days_reads_the_data_file():
    days = planner.special_days()
    # values that only exist in data/special_days.json (not in the computed fallback)
    assert "2026-07-06" in days
    assert "2026-01-13" in days
    assert len(days) > 100


def test_special_days_falls_back_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(planner, "project_root", lambda: tmp_path)
    days = planner.special_days(years=2)
    assert days and all(len(d) == 10 for d in days)


def test_choose_arm_with_full_exploration(monkeypatch):
    monkeypatch.setitem(optimizer.cfg, "optimizer", {"exploration_floor": 1.0})
    opts = ["a", "b", "c"]
    seen = {optimizer.choose_arm("hook_style", opts) for _ in range(50)}
    assert seen <= set(opts) and len(seen) > 1


def test_choose_arm_with_no_exploration_uses_posterior(monkeypatch):
    monkeypatch.setitem(optimizer.cfg, "optimizer", {"exploration_floor": 0.0})
    monkeypatch.setattr(optimizer, "thompson_sample", lambda t: "b")
    assert optimizer.choose_arm("hook_style", ["a", "b"]) == "b"


def test_choose_arm_falls_back_when_posterior_returns_unknown(monkeypatch):
    monkeypatch.setitem(optimizer.cfg, "optimizer", {"exploration_floor": 0.0})
    monkeypatch.setattr(optimizer, "thompson_sample", lambda t: "zzz")
    assert optimizer.choose_arm("hook_style", ["a", "b"]) in {"a", "b"}
