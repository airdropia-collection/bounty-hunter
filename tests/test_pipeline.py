"""Tests for the pipeline orchestrator."""
from src.scrapers.base import Bounty


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
