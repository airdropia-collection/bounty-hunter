"""Tests for the pipeline orchestrator."""
from src import pipeline
from src.scrapers.base import Bounty


def _make_bounty(repo: str, num: int) -> Bounty:
    """Helper: build a minimal IssueHunt-style bounty."""
    owner, name = repo.split("/")
    return Bounty(
        id=f"issuehunt-{owner}-{name}-{num}",
        platform="issuehunt",
        project_name=f"{repo}#{num}",
        description="test",
        max_payout_usd=10,
        severity_levels=["Low"],
        tech_stack=["GitHub"],
        source_urls=[f"https://github.com/{repo}/issues/{num}"],
        url=f"https://issuehunt.io/r/{repo}/issues/{num}",
    )


def test_bounty_dedup_key():
    b = Bounty(
        id="immunefi-test",
        platform="immunefi",
        project_name="Test",
        description="",
        max_payout_usd=0,
        severity_levels=[],
        tech_stack=[],
        source_urls=[],
        url="",
    )
    assert b.dedup_key == "immunefi:immunefi-test"


# ──────────────────────────────────────────────────────────────────── #
# verify_open_on_github (added 2026-07-17)
# ──────────────────────────────────────────────────────────────────── #
def test_verify_open_on_github_empty_list():
    """No bounties in → no bounties out."""
    assert pipeline.verify_open_on_github([]) == []


def test_verify_open_on_github_skips_closed_issues(monkeypatch):
    """If GitHub API returns state='closed', the bounty must be filtered out."""
    bounties = [_make_bounty("apache/superset", 3821)]

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"state": "closed"}

    def fake_get(url, headers=None, timeout=None, follow_redirects=None):
        assert "apache/superset/issues/3821" in url
        return FakeResp()

    monkeypatch.setattr("httpx.get", fake_get)
    # Force non-dry-run mode by setting both env vars
    monkeypatch.setenv("GH_PAT", "fake-token")
    monkeypatch.setenv("GH_REPO", "fake/repo")

    result = pipeline.verify_open_on_github(bounties)
    assert result == [], "closed issue should be filtered out"


def test_verify_open_on_github_keeps_open_issues(monkeypatch):
    """If GitHub API returns state='open', the bounty is kept."""
    bounties = [_make_bounty("apache/superset", 3821)]

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"state": "open"}

    monkeypatch.setattr("httpx.get", lambda *a, **kw: FakeResp())
    monkeypatch.setenv("GH_PAT", "fake-token")
    monkeypatch.setenv("GH_REPO", "fake/repo")

    result = pipeline.verify_open_on_github(bounties)
    assert len(result) == 1
    assert result[0].id == "issuehunt-apache-superset-3821"


def test_verify_open_on_github_keeps_on_api_error(monkeypatch):
    """If the GitHub API call fails, KEEP the bounty (fail-open)."""
    bounties = [_make_bounty("apache/superset", 3821)]

    def fake_get(*a, **kw):
        raise Exception("simulated network failure")

    monkeypatch.setattr("httpx.get", fake_get)
    monkeypatch.setenv("GH_PAT", "fake-token")
    monkeypatch.setenv("GH_REPO", "fake/repo")

    result = pipeline.verify_open_on_github(bounties)
    assert len(result) == 1, "fail-open: keep bounty when API errors"


def test_verify_open_on_github_skips_404(monkeypatch):
    """If GitHub returns 404 (issue deleted), filter out."""
    bounties = [_make_bounty("owner/repo", 999)]

    class FakeResp:
        status_code = 404

    monkeypatch.setattr("httpx.get", lambda *a, **kw: FakeResp())
    monkeypatch.setenv("GH_PAT", "fake-token")
    monkeypatch.setenv("GH_REPO", "fake/repo")

    result = pipeline.verify_open_on_github(bounties)
    assert result == [], "404 should filter out the bounty"


def test_verify_open_on_github_skips_bounties_without_github_url(monkeypatch):
    """Bounties with no github.com source URL are passed through (can't verify)."""
    b = Bounty(
        id="dework-test",
        platform="dework",
        project_name="Some DAO task",
        description="",
        max_payout_usd=100,
        severity_levels=["Medium"],
        tech_stack=["web3"],
        source_urls=[],  # no GitHub URL
        url="https://dework.xyz/task/abc",
    )
    monkeypatch.setenv("GH_PAT", "fake-token")
    monkeypatch.setenv("GH_REPO", "fake/repo")

    # Should not call httpx.get at all
    call_count = 0
    def fake_get(*a, **kw):
        nonlocal call_count
        call_count += 1
        raise AssertionError("should not call GitHub API for non-GitHub bounty")

    monkeypatch.setattr("httpx.get", fake_get)
    result = pipeline.verify_open_on_github([b])
    assert len(result) == 1
    assert call_count == 0


def test_verify_open_on_github_dry_run_skips_api(monkeypatch):
    """In dry-run mode, skip the API call entirely (preserve bounties)."""
    bounties = [_make_bounty("apache/superset", 3821)]
    # Force dry-run = True by clearing env vars (no GH_PAT or GH_REPO)
    monkeypatch.delenv("GH_PAT", raising=False)
    monkeypatch.delenv("GH_REPO", raising=False)

    call_count = 0
    def fake_get(*a, **kw):
        nonlocal call_count
        call_count += 1
        raise AssertionError("should not call API in dry-run")

    monkeypatch.setattr("httpx.get", fake_get)
    result = pipeline.verify_open_on_github(bounties)
    assert len(result) == 1
    assert call_count == 0

