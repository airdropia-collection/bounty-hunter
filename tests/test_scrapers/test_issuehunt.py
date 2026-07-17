"""Tests for the IssueHunt scraper.

Covers the JSON-parsing path (primary) and the legacy regex fallback.
The fixture HTML was captured from https://issuehunt.io/issues on
2026-07-17 and contains 18 issue objects:
  - githubState: 7 open, 11 closed
  - status: 10 ready, 8 funded (none rewarded in this fixture)
  - 7 actionable bounties after filtering (open + funded/ready + non-PR + funded>0)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.scrapers.issuehunt import IssueHuntScraper

FIXTURE = Path(__file__).parent.parent / "fixtures" / "issuehunt" / "issues.html"


@pytest.fixture
def html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def scraper(monkeypatch):
    """Build a scraper whose _fetch_html is replaced with the fixture."""
    s = IssueHuntScraper()

    def fake_fetch(url, headers=None):
        return FIXTURE.read_text(encoding="utf-8")

    monkeypatch.setattr(s, "_fetch_html", fake_fetch)
    return s


# ──────────────────────────────────────────────────────────────────── #
# End-to-end scrape (uses monkeypatched _fetch_html)
# ──────────────────────────────────────────────────────────────────── #
def test_scrape_returns_only_actionable_bounties(scraper):
    """The scraper must NOT return closed or rewarded issues."""
    bounties = scraper.scrape()
    assert len(bounties) > 0, "expected at least 1 actionable bounty in fixture"
    # All bounties must have positive payout (depositAmount > 0 cents)
    for b in bounties:
        assert b.max_payout_usd > 0, f"{b.id} has zero payout"
        assert b.platform == "issuehunt"
        assert b.url.startswith("https://issuehunt.io/r/")


def test_scrape_excludes_closed_issues(scraper):
    """Closed GitHub issues must be filtered out."""
    bounties = scraper.scrape()
    # The fixture contains ZeroCM/zcm#502 which is CLOSED on GitHub.
    # The old scraper (pre-2026-07-17) would have included it.
    ids = [b.id for b in bounties]
    assert "issuehunt-ZeroCM-zcm-502" not in ids, "closed issue leaked through filter"
    # ChestShop-3 #504 is also closed
    assert "issuehunt-ChestShop-authors-ChestShop-3-504" not in ids
    # df-mc/dragonfly #592 is also closed
    assert "issuehunt-df-mc-dragonfly-592" not in ids


def test_scrape_includes_known_open_bounty(scraper):
    """apache/incubator-superset#3821 is open + funded in the fixture."""
    bounties = scraper.scrape()
    ids = [b.id for b in bounties]
    assert "issuehunt-apache-incubator-superset-3821" in ids


def test_scrape_bounty_has_correct_payout(scraper):
    """apache/incubator-superset#3821 has depositAmount=1700 cents = $17."""
    bounties = scraper.scrape()
    by_id = {b.id: b for b in bounties}
    assert by_id["issuehunt-apache-incubator-superset-3821"].max_payout_usd == 17


def test_scrape_bounty_has_correct_github_url(scraper):
    """The source_urls must point to github.com (for ContractDownloader)."""
    bounties = scraper.scrape()
    by_id = {b.id: b for b in bounties}
    b = by_id["issuehunt-apache-incubator-superset-3821"]
    assert b.source_urls == ["https://github.com/apache/incubator-superset/issues/3821"]


def test_scrape_excludes_pull_requests(scraper, html):
    """If an issue object has isPullRequest=true, it must be skipped."""
    # Parse manually and verify no PR objects make it through
    s = scraper
    objs = s._extract_issue_objects(html)
    # Fixture may or may not have PRs, but if any PRs exist, they must be filtered
    bounties = scraper.scrape()
    # We can't directly assert PR exclusion by ID (PRs use a different ID
    # scheme), but we can assert the count matches the non-PR actionable set
    expected = [
        o for o in objs
        if o.get("githubState") == "open"
        and o.get("status") in {"ready", "funded"}
        and not o.get("isPullRequest", False)
        and (o.get("depositAmount") or 0) > 0
    ]
    assert len(bounties) == len(expected)


def test_scrape_bounty_has_tags(scraper):
    """Bounties should carry useful tags for downstream triage."""
    bounties = scraper.scrape()
    for b in bounties:
        assert "github-issue" in b.tags
        assert "bounty" in b.tags


def test_scrape_funded_bounty_marked_escrow(scraper):
    """A 'funded' status bounty should carry the escrow-funded tag."""
    bounties = scraper.scrape()
    funded = [b for b in bounties if "escrow-funded" in b.tags]
    assert len(funded) > 0, "fixture has funded bounties — expected escrow-funded tag"


# ──────────────────────────────────────────────────────────────────── #
# JSON extraction (unit-level)
# ──────────────────────────────────────────────────────────────────── #
def test_extract_issue_objects_finds_all(html):
    """The fixture has 18 issue objects — extractor must find them all."""
    s = IssueHuntScraper()
    objs = s._extract_issue_objects(html)
    assert len(objs) == 18, f"expected 18 issue objects, got {len(objs)}"


def test_extract_issue_objects_handles_malformed_html():
    """If the HTML has a truncated JSON object, extractor must not crash."""
    s = IssueHuntScraper()
    # Truncated object (no closing brace)
    bad_html = '<html>{"isPullRequest":false,"githubState":"open"'
    objs = s._extract_issue_objects(bad_html)
    assert objs == [], "truncated JSON should yield zero objects, not crash"


def test_extract_issue_objects_empty_html():
    s = IssueHuntScraper()
    assert s._extract_issue_objects("") == []
    assert s._extract_issue_objects("<html>no json here</html>") == []


# ──────────────────────────────────────────────────────────────────── #
# Bounty from JSON (unit-level)
# ──────────────────────────────────────────────────────────────────── #
def test_bounty_from_json_open_funded():
    """A well-formed open+funded issue must produce a Bounty."""
    s = IssueHuntScraper()
    obj = {
        "isPullRequest": False,
        "githubState": "open",
        "status": "funded",
        "depositAmount": 5000,  # $50
        "repositoryOwnerName": "owner",
        "repositoryName": "repo",
        "number": 42,
        "title": "Test issue",
        "fundedAt": "2026-01-01T00:00:00Z",
        "pullRequestCount": 0,
    }
    b = s._bounty_from_json(obj)
    assert b is not None
    assert b.id == "issuehunt-owner-repo-42"
    assert b.max_payout_usd == 50
    assert b.project_name == "owner/repo#42"
    assert "escrow-funded" in b.tags
    assert "no-competing-pr" in b.tags


def test_bounty_from_json_closed_state_returns_none():
    """Closed GitHub issues must be filtered out (returns None)."""
    s = IssueHuntScraper()
    obj = {"isPullRequest": False, "githubState": "closed", "status": "funded", "depositAmount": 1000}
    assert s._bounty_from_json(obj) is None


def test_bounty_from_json_rewarded_status_returns_none():
    """Already-rewarded (paid out) bounties must be filtered out."""
    s = IssueHuntScraper()
    obj = {"isPullRequest": False, "githubState": "open", "status": "rewarded", "depositAmount": 1000}
    assert s._bounty_from_json(obj) is None


def test_bounty_from_json_pull_request_returns_none():
    """Pull requests (not issues) must be filtered out."""
    s = IssueHuntScraper()
    obj = {"isPullRequest": True, "githubState": "open", "status": "funded", "depositAmount": 1000}
    assert s._bounty_from_json(obj) is None


def test_bounty_from_json_zero_deposit_returns_none():
    """Zero-deposit bounties (unfunded 'ready') must be filtered out."""
    s = IssueHuntScraper()
    obj = {"isPullRequest": False, "githubState": "open", "status": "ready", "depositAmount": 0}
    assert s._bounty_from_json(obj) is None


def test_bounty_from_json_missing_fields_returns_none():
    """Objects missing required identity fields must be skipped."""
    s = IssueHuntScraper()
    obj = {"isPullRequest": False, "githubState": "open", "status": "funded", "depositAmount": 1000}
    # No repositoryOwnerName / repositoryName / number
    assert s._bounty_from_json(obj) is None


def test_bounty_from_json_cents_to_dollars_truncates():
    """depositAmount=1799 cents → $17 (integer truncation, not rounding)."""
    s = IssueHuntScraper()
    obj = {
        "isPullRequest": False,
        "githubState": "open",
        "status": "funded",
        "depositAmount": 1799,
        "repositoryOwnerName": "o",
        "repositoryName": "r",
        "number": 1,
    }
    b = s._bounty_from_json(obj)
    assert b is not None
    assert b.max_payout_usd == 17  # 1799 // 100 = 17 (integer truncation)


# ──────────────────────────────────────────────────────────────────── #
# Legacy fallback
# ──────────────────────────────────────────────────────────────────── #
def test_legacy_regex_parse_returns_empty_on_no_links():
    """If JSON parsing fails AND no /r/ links exist, must return []."""
    s = IssueHuntScraper()
    result = s._legacy_regex_parse("<html>no links here</html>")
    assert result == []


def test_legacy_regex_parse_finds_links():
    """If JSON parsing fails, legacy parser should still find /r/ links."""
    s = IssueHuntScraper()
    html = '<a href="/r/owner/repo/issues/123">link</a>'
    result = s._legacy_regex_parse(html)
    assert len(result) == 1
    assert result[0].id == "issuehunt-owner-repo-123"
    assert "unverified-status" in result[0].tags


def test_legacy_regex_parse_dedupes():
    """Duplicate links should only be counted once."""
    s = IssueHuntScraper()
    html = '<a href="/r/o/r/issues/1">x</a><a href="/r/o/r/issues/1">x</a>'
    result = s._legacy_regex_parse(html)
    assert len(result) == 1
