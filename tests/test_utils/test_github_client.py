"""Tests for the GitHub client."""
import pytest

from src.utils.github_client import (
    ALL_LABELS,
    LABEL_BOUNTY_FINDING,
    LABEL_OPERATOR_NEEDED,
    GitHubClient,
    Issue,
)


@pytest.fixture
def dry_run_client(monkeypatch):
    """A GitHubClient in dry-run mode (no token, no repo)."""
    monkeypatch.delenv("GH_PAT", raising=False)
    monkeypatch.delenv("GH_REPO", raising=False)
    return GitHubClient()


def test_dry_run_mode_when_no_credentials(dry_run_client):
    assert dry_run_client._dry_run is True


def test_dry_run_create_issue_returns_none(dry_run_client):
    issue = dry_run_client.create_issue("test title", "test body", labels=["test"])
    assert issue is None


def test_dry_run_wake_operator_returns_none(dry_run_client):
    issue = dry_run_client.wake_operator(
        title="Missing secret",
        body="I need GEMINI_API_KEY",
        category="missing_secret",
    )
    assert issue is None


def test_dry_run_comment_issue_no_crash(dry_run_client):
    dry_run_client.comment_issue(123, "test comment")


def test_dry_run_close_issue_no_crash(dry_run_client):
    dry_run_client.close_issue(123)


def test_dry_run_list_open_issues_returns_empty(dry_run_client):
    assert dry_run_client.list_open_issues() == []


def test_dry_run_is_operator_needed_returns_false(dry_run_client):
    assert dry_run_client.is_operator_needed() is False


def test_label_color_mapping():
    assert GitHubClient._label_color(LABEL_OPERATOR_NEEDED) == "d73a4a"
    assert GitHubClient._label_color(LABEL_BOUNTY_FINDING) == "fbca04"
    assert GitHubClient._label_color("unknown") == "ededed"


def test_label_description_mapping():
    desc = GitHubClient._label_description(LABEL_OPERATOR_NEEDED)
    assert "human input" in desc.lower()


def test_all_labels_defined():
    assert LABEL_OPERATOR_NEEDED in ALL_LABELS
    assert LABEL_BOUNTY_FINDING in ALL_LABELS
    assert len(ALL_LABELS) >= 6


def test_wake_operator_with_context(dry_run_client):
    issue = dry_run_client.wake_operator(
        title="Ambiguous finding",
        body="I found something but I'm not sure",
        category="ambiguous_finding",
        context={
            "bounty_id": "immunefi-123",
            "severity": "medium",
            "confidence": 0.4,
            "ai_model": "gemini",
        },
    )
    assert issue is None  # dry-run


def test_client_with_credentials(monkeypatch):
    """When GH_PAT and GH_REPO are set, dry_run should be False."""
    monkeypatch.setenv("GH_PAT", "ghp_FAKE_TOKEN_PLACEHOLDER")
    monkeypatch.setenv("GH_REPO", "test/repo")
    client = GitHubClient()
    assert client._dry_run is False
    assert client.token == "ghp_FAKE_TOKEN_PLACEHOLDER"
    assert client.repo == "test/repo"


def test_issue_dataclass():
    issue = Issue(
        number=42,
        title="Test",
        body="Body",
        labels=["bug"],
        url="https://github.com/test/repo/issues/42",
        state="open",
    )
    assert issue.number == 42
    assert issue.state == "open"
