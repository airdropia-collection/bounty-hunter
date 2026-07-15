"""Tests for the State class."""
import json
from pathlib import Path

from src.utils.state import State


def test_empty_state(tmp_path):
    s = State("test", state_dir=tmp_path, ttl_hours=24)
    assert not s.has("anything")
    assert s.count() == 0
    assert s.filter_unseen(["x"]) == ["x"]


def test_add_then_has(tmp_path):
    s = State("test", state_dir=tmp_path, ttl_hours=24)
    s.add("k1", data={"reward": 500}, status="seen")
    assert s.has("k1")
    assert not s.has("k2")
    assert s.get("k1") == {"reward": 500}


def test_filter_unseen_skips_existing(tmp_path):
    s = State("test", state_dir=tmp_path, ttl_hours=24)
    s.add("k1", status="seen")
    keys = ["k1", "k2", "k3"]
    assert s.filter_unseen(keys) == ["k2", "k3"]


def test_state_persists_across_instances(tmp_path):
    p = tmp_path / "state"
    s1 = State("test", state_dir=p, ttl_hours=24)
    s1.add("k1", data={"v": 1}, status="seen")
    s2 = State("test", state_dir=p, ttl_hours=24)
    assert s2.has("k1")
    assert s2.get("k1") == {"v": 1}


def test_update_status(tmp_path):
    s = State("test", state_dir=tmp_path, ttl_hours=24)
    s.add("k1", status="seen")
    assert s.update_status("k1", "submitted")
    assert s._data["items"]["k1"]["status"] == "submitted"
    assert not s.update_status("nonexistent", "x")


def test_prune_removes_old_entries(tmp_path):
    p = tmp_path / "state"
    s = State("test", state_dir=p, ttl_hours=1)
    # Inject an old entry manually
    s._data["items"] = {
        "old": {
            "added_at": "2000-01-01T00:00:00+00:00",
            "status": "seen",
            "data": None,
        },
        "new": {
            "added_at": "2099-01-01T00:00:00+00:00",
            "status": "seen",
            "data": None,
        },
    }
    s._save()
    pruned = s.prune()
    assert pruned == 1
    assert not s.has("old")
    assert s.has("new")


def test_count_by_status(tmp_path):
    s = State("test", state_dir=tmp_path, ttl_hours=24)
    s.add("k1", status="seen")
    s.add("k2", status="seen")
    s.add("k3", status="submitted")
    counts = s.count_by_status()
    assert counts == {"seen": 2, "submitted": 1}


def test_all_items_returns_copy(tmp_path):
    s = State("test", state_dir=tmp_path, ttl_hours=24)
    s.add("k1", status="seen")
    items = s.all_items()
    items["injected"] = {}
    # Modifying returned dict should not affect state
    assert "injected" not in s.all_items()


def test_ttl_expiry(tmp_path):
    p = tmp_path / "state"
    s = State("test", state_dir=p, ttl_hours=1)
    # Add old entry
    s._data["items"] = {
        "old": {
            "added_at": "2000-01-01T00:00:00+00:00",
            "status": "seen",
            "data": None,
        }
    }
    s._save()
    s2 = State("test", state_dir=p, ttl_hours=1)
    assert not s2.has("old")  # expired
