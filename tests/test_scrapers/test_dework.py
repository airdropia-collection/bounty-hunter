"""Tests for the Dework scraper.

Focus: identity-reveal (KYC) and non-code-task filtering.
Added 2026-07-17 after operator directive to auto-skip KYC bounties.
"""
from __future__ import annotations

from src.scrapers.dework import DeworkScraper


def _make_task(
    task_id: str = "test-1",
    name: str = "Implement feature X",
    description: str = "Build the feature, submit PR.",
    rewards: list[dict] | None = None,
) -> dict:
    if rewards is None:
        rewards = [{
            "amount": "1000000000",  # 1000 USDC
            "type": "FIXED",
            "token": {"symbol": "USDC", "address": ""},
        }]
    return {
        "id": task_id,
        "name": name,
        "description": description,
        "rewards": rewards,
        "status": "TODO",
    }


def _make_scraper() -> DeworkScraper:
    return DeworkScraper()


# ──────────────────────────────────────────────────────────────────── #
# Identity-reveal (KYC) filtering
# ──────────────────────────────────────────────────────────────────── #
def test_kyc_in_description_filtered():
    """Bounty description mentioning KYC must be filtered out."""
    s = _make_scraper()
    task = _make_task(description="**KYC will be required for disbursement.**")
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_kyc_phrase_filtered():
    """'know your customer' phrase must be filtered."""
    s = _make_scraper()
    task = _make_task(description="Payment requires know your customer verification.")
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_invoice_submission_filtered():
    """Bounty requiring invoice submission must be filtered."""
    s = _make_scraper()
    task = _make_task(description="Payment will require submitting an invoice and revealing your identity.")
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_government_id_filtered():
    """Bounty requiring government ID must be filtered."""
    s = _make_scraper()
    task = _make_task(description="Please upload a government id for verification.")
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_passport_filtered():
    """Bounty requiring passport must be filtered."""
    s = _make_scraper()
    task = _make_task(description="Scan of passport required for payout.")
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_w9_tax_form_filtered():
    """W-9 tax form requirement must be filtered."""
    s = _make_scraper()
    task = _make_task(description="Submit W-9 form before payment can be processed.")
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_kyc_case_insensitive():
    """KYC filter must be case-insensitive."""
    s = _make_scraper()
    task = _make_task(description="Kyc is required for this bounty.")
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_kyc_in_name_filtered():
    """KYC marker in task NAME (not just description) must be filtered."""
    s = _make_scraper()
    task = _make_task(name="KYC Required: Build dashboard")
    assert s._bounty_from_task(task, "Org", "WS") is None


# ──────────────────────────────────────────────────────────────────── #
# Non-code-task filtering
# ──────────────────────────────────────────────────────────────────── #
def test_community_moderator_filtered():
    """'Community Moderator' task must be filtered (non-code)."""
    s = _make_scraper()
    task = _make_task(name="October 2025 - Community Moderator - Weekday evenings")
    assert s._bounty_from_task(task, "DIA DAO", "Operations Guild") is None


def test_telegram_growth_filtered():
    """'Telegram Growth' task must be filtered (non-code)."""
    s = _make_scraper()
    task = _make_task(name="Telegram Growth Specialist")
    assert s._bounty_from_task(task, "CyberConnect", "Telegram Growth") is None


def test_discord_moderator_filtered():
    s = _make_scraper()
    task = _make_task(name="Discord Moderator Wanted")
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_social_media_manager_filtered():
    s = _make_scraper()
    task = _make_task(name="Social Media Manager for DAO")
    assert s._bounty_from_task(task, "Org", "WS") is None


# ──────────────────────────────────────────────────────────────────── #
# Positive cases (must NOT be filtered)
# ──────────────────────────────────────────────────────────────────── #
def test_normal_code_bounty_passes():
    """A normal code bounty with no KYC/non-code markers must pass through."""
    s = _make_scraper()
    task = _make_task(
        name="Implement staking contract audit",
        description="Audit the staking contract for vulnerabilities. Submit PR with fixes.",
    )
    result = s._bounty_from_task(task, "TestOrg", "TestWS")
    assert result is not None
    assert result.id == "dework-test-1"
    assert result.max_payout_usd == 1000


def test_bounty_with_community_in_description_passes():
    """Description mentioning 'community' (but not as the task type) must pass.

    Many code tasks reference community in passing — we only filter when the
    NAME indicates non-code work, not when description mentions community.
    """
    s = _make_scraper()
    task = _make_task(
        name="Add community-submitted feature to dashboard",
        description="The community has requested this feature.",
    )
    result = s._bounty_from_task(task, "Org", "WS")
    assert result is not None, "community in description should NOT trigger filter"


def test_bounty_with_invoice_in_unrelated_context_passes():
    """The word 'invoice' in a non-KYC context (e.g. 'invoice generation feature') should pass.

    Wait — we DO filter on 'submit an invoice' and 'submitting an invoice'.
    But 'invoice generation feature' should not match those exact phrases.
    """
    s = _make_scraper()
    task = _make_task(
        name="Build invoice generation feature",
        description="Users want to generate invoices for their customers.",
    )
    result = s._bounty_from_task(task, "Org", "WS")
    # 'invoice' alone doesn't match our exact phrases like 'submit an invoice'
    assert result is not None, "invoice in feature context should NOT trigger filter"


# ──────────────────────────────────────────────────────────────────── #
# Cycle 19: positive code-keyword requirement (Layer 2)
# ──────────────────────────────────────────────────────────────────── #
def test_regional_lead_filtered_no_code_keyword():
    """Cycle 19 CyberConnect case: 'Regional Lead' has no code keyword → filtered."""
    s = _make_scraper()
    task = _make_task(
        name="Regional Lead",
        description="Lead our regional community growth efforts.",
    )
    assert s._bounty_from_task(task, "CyberConnect", "Telegram Growth") is None


def test_growth_lead_filtered_no_code_keyword():
    """'Growth Lead' without code keywords → filtered (Cycle 19)."""
    s = _make_scraper()
    task = _make_task(
        name="Growth Lead",
        description="Drive user acquisition and engagement.",
    )
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_ambassador_filtered():
    """'Ambassador' role → filtered (Cycle 19 addition to blacklist)."""
    s = _make_scraper()
    task = _make_task(name="DAO Ambassador Program")
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_evangelist_filtered():
    """'Evangelist' role → filtered (Cycle 19 addition to blacklist)."""
    s = _make_scraper()
    task = _make_task(name="Developer Evangelist Wanted")
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_vague_title_with_code_keyword_in_desc_passes():
    """Vague title but description has code keyword → passes (Layer 2 whitelist).

    Example: title='Help needed' but description='Fix the auth bug in login flow'
    should pass because 'fix' and 'bug' are code keywords.
    """
    s = _make_scraper()
    task = _make_task(
        name="Help needed",
        description="Fix the auth bug in the login flow. Submit PR with tests.",
    )
    result = s._bounty_from_task(task, "Org", "WS")
    assert result is not None, "code keywords in description should pass Layer 2"


def test_vague_title_no_code_keyword_anywhere_filtered():
    """Vague title + vague description → filtered (Layer 2 catches it)."""
    s = _make_scraper()
    task = _make_task(
        name="Help needed",
        description="We need someone to assist with our community efforts.",
    )
    assert s._bounty_from_task(task, "Org", "WS") is None


def test_code_keyword_in_name_passes():
    """Code keyword in title alone (no description) → passes."""
    s = _make_scraper()
    task = _make_task(name="Implement webhook retry logic")
    result = s._bounty_from_task(task, "Org", "WS")
    assert result is not None, "code keyword in name should pass Layer 2"


def test_tech_stack_keyword_passes():
    """Tech-stack keyword (python, rust, react, etc.) → passes."""
    s = _make_scraper()
    task = _make_task(
        name="Add metrics endpoint",
        description="Expose Prometheus metrics via python FastAPI endpoint.",
    )
    result = s._bounty_from_task(task, "Org", "WS")
    assert result is not None


def test_docs_keyword_passes():
    """'docs' / 'documentation' / 'readme' count as code keywords (technical writing)."""
    s = _make_scraper()
    task = _make_task(
        name="Improve API documentation",
        description="Update the OpenAPI spec and README examples.",
    )
    result = s._bounty_from_task(task, "Org", "WS")
    assert result is not None, "documentation is a code-adjacent task"
