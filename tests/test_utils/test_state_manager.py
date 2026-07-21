"""Tests for state_manager — central state authority.

These tests use monkeypatch to redirect STATE_FILE to a tmp_path so they
never touch the production state.json in the repo root.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.utils import state_manager


@pytest.fixture
def state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect state_manager.STATE_FILE to an isolated tmp_path."""
    path = tmp_path / "state.json"
    monkeypatch.setattr(state_manager, "STATE_FILE", path)
    return path


# ──────────────────────────────────────────────────────────────────── #
# _normalize_repo_key
# ──────────────────────────────────────────────────────────────────── #
def test_normalize_strips_issue_suffix():
    assert state_manager._normalize_repo_key("owner/repo#3") == "owner/repo"
    assert state_manager._normalize_repo_key("owner/repo") == "owner/repo"
    assert state_manager._normalize_repo_key("a/b#99") == "a/b"


# ──────────────────────────────────────────────────────────────────── #
# find_monitor_by_pr
# ──────────────────────────────────────────────────────────────────── #
def test_find_monitor_returns_none_when_empty(state_file: Path):
    assert state_manager.find_monitor_by_pr("owner/repo", 5) is None


def test_find_monitor_matches_bare_key(state_file: Path):
    state_manager.add_monitor("owner/repo", 5)
    assert state_manager.find_monitor_by_pr("owner/repo", 5) == "owner/repo"


def test_find_monitor_matches_suffixed_key(state_file: Path):
    """If state.json already has 'owner/repo#3', searching for ('owner/repo', pr)
    must find it — this is the Cycle 15 dedup scenario."""
    state_manager.add_monitor("owner/repo#3", 5)
    # Search with bare repo key
    assert state_manager.find_monitor_by_pr("owner/repo", 5) == "owner/repo#3"
    # Search with suffixed key
    assert state_manager.find_monitor_by_pr("owner/repo#3", 5) == "owner/repo#3"
    # Search with different issue suffix but same pr — should still match
    # (because both keys normalize to the same repo)
    assert state_manager.find_monitor_by_pr("owner/repo#99", 5) == "owner/repo#3"


def test_find_monitor_does_not_match_different_repo(state_file: Path):
    state_manager.add_monitor("owner/repo", 5)
    assert state_manager.find_monitor_by_pr("other/repo", 5) is None


def test_find_monitor_does_not_match_different_pr(state_file: Path):
    state_manager.add_monitor("owner/repo", 5)
    assert state_manager.find_monitor_by_pr("owner/repo", 6) is None


def test_find_monitor_handles_string_pr_number(state_file: Path):
    state_manager.add_monitor("owner/repo", 5)
    # String "5" should match int 5 (defensive — workflows may pass strings)
    assert state_manager.find_monitor_by_pr("owner/repo", "5") == "owner/repo"


# ──────────────────────────────────────────────────────────────────── #
# add_monitor — dedup guard (the Cycle 15 fix)
# ──────────────────────────────────────────────────────────────────── #
def test_add_monitor_returns_true_on_new_pr(state_file: Path):
    assert state_manager.add_monitor("owner/repo", 5) is True
    assert state_manager.get_monitor("owner/repo") is not None


def test_add_monitor_returns_false_on_dup_same_key(state_file: Path):
    """Re-adding with identical key+pr must skip (idempotent retry)."""
    assert state_manager.add_monitor("owner/repo", 5) is True
    assert state_manager.add_monitor("owner/repo", 5) is False
    # State file must not have a duplicate entry
    state = json.loads(state_file.read_text())
    assert len(state["active_monitors"]) == 1


def test_add_monitor_returns_false_on_dup_cross_key_format(state_file: Path):
    """The actual Cycle 15 root cause: bare key + suffixed key for same PR.

    If 'owner/repo' is already tracked for PR #5, then add_monitor('owner/repo#3', 5)
    must skip — both refer to the same upstream PR.
    """
    assert state_manager.add_monitor("owner/repo", 5) is True
    assert state_manager.add_monitor("owner/repo#3", 5) is False
    state = json.loads(state_file.read_text())
    assert len(state["active_monitors"]) == 1
    assert "owner/repo" in state["active_monitors"]
    assert "owner/repo#3" not in state["active_monitors"]


def test_add_monitor_reverse_cross_key_format(state_file: Path):
    """Reverse: if 'owner/repo#3' is tracked first, then 'owner/repo' must skip."""
    assert state_manager.add_monitor("owner/repo#3", 5) is True
    assert state_manager.add_monitor("owner/repo", 5) is False
    state = json.loads(state_file.read_text())
    assert len(state["active_monitors"]) == 1


def test_add_monitor_overwrites_same_repo_different_pr(state_file: Path):
    """Known design limitation: ``add_monitor`` keys by ``repo`` arg, so adding
    a second PR to the same upstream repo OVERWRITES the first entry.

    This is why the ``#N`` suffix convention exists for repos with multiple
    concurrent PRs (e.g. CBB has 3 active PRs tracked as
    ``claude-builders-bounty/claude-builders-bounty#1``, ``#3``, ``#4``).
    Callers needing multiple PRs per repo must pass distinct ``repo#N`` keys.

    The dedup guard added in Cycle 16 specifically prevents the inverse
    failure (same PR registered under two different keys), not this one.
    """
    assert state_manager.add_monitor("owner/repo", 5) is True
    # Second add returns True (not a dup) but silently OVERWRITES the first
    assert state_manager.add_monitor("owner/repo", 6) is True
    state = json.loads(state_file.read_text())
    # Only one entry — the latest PR number wins
    assert len(state["active_monitors"]) == 1
    assert state["active_monitors"]["owner/repo"]["pr_number"] == 6


def test_add_monitor_supports_multiple_prs_via_suffix_keys(state_file: Path):
    """The ``#N`` suffix convention lets multiple PRs coexist on the same repo.

    This is the pattern used in production for Opire-bountied CBB issues:
    ``owner/repo#1``, ``owner/repo#3``, ``owner/repo#4`` are three distinct
    monitors tracking three distinct PRs on the same upstream repo.
    """
    assert state_manager.add_monitor("owner/repo#1", 100) is True
    assert state_manager.add_monitor("owner/repo#3", 200) is True
    assert state_manager.add_monitor("owner/repo#4", 300) is True
    state = json.loads(state_file.read_text())
    assert len(state["active_monitors"]) == 3
    # All three coexist
    assert state["active_monitors"]["owner/repo#1"]["pr_number"] == 100
    assert state["active_monitors"]["owner/repo#3"]["pr_number"] == 200
    assert state["active_monitors"]["owner/repo#4"]["pr_number"] == 300


# ──────────────────────────────────────────────────────────────────── #
# Smoke: read_state / write_state round-trip
# ──────────────────────────────────────────────────────────────────── #
def test_read_state_returns_defaults_when_missing(state_file: Path):
    state = state_manager.read_state()
    assert state["system_status"] == "RUNNING"
    assert state["active_monitors"] == {}


def test_write_then_read_roundtrips(state_file: Path):
    state_manager.add_monitor("a/b", 1, bounty_value="$50", platform="Opire")
    state = state_manager.read_state()
    assert "a/b" in state["active_monitors"]
    assert state["active_monitors"]["a/b"]["pr_number"] == 1
    assert state["active_monitors"]["a/b"]["bounty_value"] == "$50"
    assert state["active_monitors"]["a/b"]["platform"] == "Opire"


# ──────────────────────────────────────────────────────────────────── #
# Pause / resume
# ──────────────────────────────────────────────────────────────────── #
def test_pause_then_is_paused(state_file: Path):
    assert state_manager.is_paused() is False
    assert state_manager.pause() is True
    assert state_manager.is_paused() is True
    # Second pause is a no-op
    assert state_manager.pause() is False


def test_resume_after_pause(state_file: Path):
    state_manager.pause()
    assert state_manager.resume() is True
    assert state_manager.is_running() is True
    # Second resume is a no-op
    assert state_manager.resume() is False
