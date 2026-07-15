"""Tests for the Bounty dataclass."""
from src.scrapers.base import Bounty


def test_bounty_creation():
    b = Bounty(
        id="immunefi-aave",
        platform="immunefi",
        project_name="Aave",
        description="Bug bounty for Aave",
        max_payout_usd=1_000_000,
        severity_levels=["Critical", "High"],
        tech_stack=["Solidity"],
        source_urls=["https://github.com/aave/aave-v3"],
        url="https://immunefi.com/bounty/aave",
    )
    assert b.project_name == "Aave"
    assert b.max_payout_usd == 1_000_000
    assert b.status == "active"


def test_bounty_dedup_key():
    b = Bounty(
        id="immunefi-aave",
        platform="immunefi",
        project_name="Aave",
        description="",
        max_payout_usd=0,
        severity_levels=[],
        tech_stack=[],
        source_urls=[],
        url="",
    )
    assert b.dedup_key == "immunefi:immunefi-aave"


def test_bounty_to_dict():
    b = Bounty(
        id="test-1",
        platform="immunefi",
        project_name="Test",
        description="desc",
        max_payout_usd=5000,
        severity_levels=["High"],
        tech_stack=["Solidity"],
        source_urls=[],
        url="https://example.com",
    )
    d = b.to_dict()
    assert d["id"] == "test-1"
    assert d["platform"] == "immunefi"
    assert d["max_payout_usd"] == 5000
    assert "scraped_at" in d


def test_bounty_defaults():
    b = Bounty(
        id="x",
        platform="immunefi",
        project_name="X",
        description="",
        max_payout_usd=0,
        severity_levels=[],
        tech_stack=[],
        source_urls=[],
        url="",
    )
    assert b.status == "active"
    assert b.deadline is None
    assert b.tags == []
    assert b.scraped_at  # auto-generated
