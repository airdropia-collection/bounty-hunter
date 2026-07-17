"""Platform scrapers for bug bounty listings.

VERIFIED-PLATFORMS-ONLY POLICY (per user directive 2026-07-17):

The bot ONLY scrapes bounty listings from these two verified escrow
platforms. Random GitHub issues claiming cash rewards are IGNORED
unless they appear via one of these platforms:

1. IssueHunt — https://issuehunt.io (public, no auth)
2. Dework    — https://dework.xyz (Web3 task manager for DAOs;
                public API returns org + workspace metadata;
                task data requires DEWORK_AUTH_TOKEN env var)

⚠️ Bountycaster was REMOVED on 2026-07-17 (required Privy/Farcaster auth
   which was useless for our autonomous execution).
⚠️ Algora was REMOVED on 2026-07-17 (pivoted to recruiting marketplace).
⚠️ Dework was ADDED on 2026-07-17 to replace Bountycaster (Web3 DAO
   bounties with crypto payouts).

The legacy Immunefi, Code4rena, and Sherlock scrapers are kept for
manual reference but are NOT included in the default SCRAPER_MAP in
pipeline.py. To re-enable them, set the INCLUDE_LEGACY_SCRAPERS env
var to "true".
"""

from .base import BaseScraper, Bounty

# Legacy scrapers (kept for manual use, NOT in default SCRAPER_MAP)
from .code4rena import Code4renaScraper
from .dework import DeworkScraper
from .immunefi import ImmunefiScraper
from .issuehunt import IssueHuntScraper
from .sherlock import SherlockScraper

__all__ = [
    "BaseScraper",
    "Bounty",
    # Verified escrow platforms (default scraping)
    "IssueHuntScraper",
    "DeworkScraper",
    # Legacy platforms (manual only)
    "ImmunefiScraper",
    "Code4renaScraper",
    "SherlockScraper",
]
