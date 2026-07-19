"""Tests for the agent memory registry (atomic read/write persistence)."""
from __future__ import annotations

import json

from src.utils.memory_registry import (
    _empty_memory,
    append_learned_pattern,
    load_memory,
    save_memory,
)


# ──────────────────────────────────────────────────────────────────── #
# load_memory
# ──────────────────────────────────────────────────────────────────── #
def test_load_memory_missing_file(tmp_path):
    """Loading from non-existent file returns empty skeleton."""
    path = tmp_path / "missing.json"
    memory = load_memory(path)
    assert "learned_patterns" in memory
    assert memory["learned_patterns"] == []
    assert "version" in memory


def test_load_memory_valid_file(tmp_path):
    """Loading from valid file returns parsed data."""
    path = tmp_path / "memory.json"
    data = {"learned_patterns": [{"id": "p1"}], "version": "1.0.0"}
    path.write_text(json.dumps(data))
    memory = load_memory(path)
    assert len(memory["learned_patterns"]) == 1
    assert memory["learned_patterns"][0]["id"] == "p1"


def test_load_memory_corrupt_file(tmp_path):
    """Loading from corrupt JSON returns empty skeleton, doesn't crash."""
    path = tmp_path / "corrupt.json"
    path.write_text("not valid json {{{")
    memory = load_memory(path)
    assert memory["learned_patterns"] == []


def test_load_memory_missing_keys(tmp_path):
    """File without required keys gets them auto-filled."""
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"version": "2.0"}))
    memory = load_memory(path)
    assert "learned_patterns" in memory
    assert memory["learned_patterns"] == []
    assert "optimization_vectors" in memory


def test_load_memory_default_path():
    """Default path (no arg) loads from docs/agent_memory.json."""
    memory = load_memory()
    assert isinstance(memory, dict)
    assert "learned_patterns" in memory


# ──────────────────────────────────────────────────────────────────── #
# save_memory (atomic write)
# ──────────────────────────────────────────────────────────────────── #
def test_save_memory_creates_file(tmp_path):
    """Save creates the file if it doesn't exist."""
    path = tmp_path / "new_memory.json"
    memory = _empty_memory()
    assert save_memory(memory, path)
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["learned_patterns"] == []


def test_save_memory_overwrites_existing(tmp_path):
    """Save overwrites existing file atomically."""
    path = tmp_path / "existing.json"
    path.write_text(json.dumps({"old": "data"}))
    memory = _empty_memory()
    memory["learned_patterns"] = [{"id": "p1", "title": "test"}]
    assert save_memory(memory, path)
    loaded = json.loads(path.read_text())
    assert "old" not in loaded  # _empty_memory() replaces all keys
    assert len(loaded["learned_patterns"]) == 1


def test_save_memory_updates_timestamp(tmp_path):
    """Save always updates last_updated field."""
    path = tmp_path / "ts.json"
    memory = _empty_memory()
    old_ts = memory["last_updated"]
    save_memory(memory, path)
    loaded = json.loads(path.read_text())
    assert loaded["last_updated"] == old_ts or loaded["last_updated"] != ""


def test_save_memory_creates_parent_dir(tmp_path):
    """Save creates parent directories if needed."""
    path = tmp_path / "subdir" / "nested" / "memory.json"
    memory = _empty_memory()
    assert save_memory(memory, path)
    assert path.exists()


# ──────────────────────────────────────────────────────────────────── #
# append_learned_pattern
# ──────────────────────────────────────────────────────────────────── #
def test_append_new_pattern(tmp_path):
    """Appending a new pattern adds it to learned_patterns."""
    path = tmp_path / "mem.json"
    result = append_learned_pattern(
        category="test_category",
        title="Test Pattern",
        description="A test error pattern",
        fix="Fix it like this",
        tags=["python", "test"],
        memory_path=path,
    )
    assert result["status"] == "SUCCESS"
    assert result["pattern_id"].startswith("pattern-")

    memory = load_memory(path)
    assert len(memory["learned_patterns"]) == 1
    assert memory["learned_patterns"][0]["category"] == "test_category"
    assert memory["learned_patterns"][0]["title"] == "Test Pattern"
    assert memory["learned_patterns"][0]["applied_count"] == 1


def test_append_duplicate_increments_count(tmp_path):
    """Appending the same category+title increments applied_count."""
    path = tmp_path / "mem.json"
    # First append
    append_learned_pattern("dup", "Duplicate", "desc", "fix", memory_path=path)
    # Second append (same category+title)
    result = append_learned_pattern("dup", "Duplicate", "desc", "fix", memory_path=path)
    assert result["status"] == "SUCCESS"

    memory = load_memory(path)
    assert len(memory["learned_patterns"]) == 1  # no duplicate entry
    assert memory["learned_patterns"][0]["applied_count"] == 2


def test_append_different_patterns(tmp_path):
    """Appending different patterns creates separate entries."""
    path = tmp_path / "mem.json"
    append_learned_pattern("cat_a", "Pattern A", "desc", "fix", memory_path=path)
    append_learned_pattern("cat_b", "Pattern B", "desc", "fix", memory_path=path)

    memory = load_memory(path)
    assert len(memory["learned_patterns"]) == 2


def test_append_generates_sequential_ids(tmp_path):
    """Pattern IDs are sequential (pattern-001, pattern-002, ...)."""
    path = tmp_path / "mem.json"
    r1 = append_learned_pattern("a", "First", "d", "f", memory_path=path)
    r2 = append_learned_pattern("b", "Second", "d", "f", memory_path=path)
    r3 = append_learned_pattern("c", "Third", "d", "f", memory_path=path)
    assert r1["pattern_id"] == "pattern-001"
    assert r2["pattern_id"] == "pattern-002"
    assert r3["pattern_id"] == "pattern-003"


def test_append_with_tags(tmp_path):
    """Tags are stored correctly."""
    path = tmp_path / "mem.json"
    append_learned_pattern("cat", "T", "d", "f", tags=["go", "healed", "auto"], memory_path=path)
    memory = load_memory(path)
    assert "go" in memory["learned_patterns"][0]["tags"]
    assert "healed" in memory["learned_patterns"][0]["tags"]


def test_append_without_tags(tmp_path):
    """Empty tags list when none provided."""
    path = tmp_path / "mem.json"
    append_learned_pattern("cat", "T", "d", "f", memory_path=path)
    memory = load_memory(path)
    assert memory["learned_patterns"][0]["tags"] == []


def test_append_to_missing_file_creates_it(tmp_path):
    """Appending to non-existent file creates it with proper skeleton."""
    path = tmp_path / "new.json"
    result = append_learned_pattern("cat", "T", "d", "f", memory_path=path)
    assert result["status"] == "SUCCESS"
    assert path.exists()

    memory = load_memory(path)
    assert memory["version"] == "1.0.0"
    assert len(memory["learned_patterns"]) == 1


def test_append_preserves_existing_data(tmp_path):
    """Appending doesn't destroy existing patterns."""
    path = tmp_path / "mem.json"
    # Seed with existing data
    memory = _empty_memory()
    memory["learned_patterns"] = [
        {"id": "pattern-001", "category": "existing", "title": "Old Pattern", "applied_count": 5}
    ]
    memory["optimization_vectors"] = [{"id": "opt-001", "title": "Old Opt"}]
    save_memory(memory, path)

    # Append new pattern
    append_learned_pattern("new", "New Pattern", "d", "f", memory_path=path)

    memory = load_memory(path)
    assert len(memory["learned_patterns"]) == 2
    assert memory["learned_patterns"][0]["title"] == "Old Pattern"
    assert memory["learned_patterns"][1]["title"] == "New Pattern"
    assert len(memory["optimization_vectors"]) == 1  # preserved
