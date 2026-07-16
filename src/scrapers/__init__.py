"""Platform scrapers for bug bounty listings.

VERIFIED-PLATFORMS-ONLY POLICY (per user directive 2026-07-16):
The bot ONLY scrapes bounty listings from these three verified escrow
platforms. Random GitHub issues claiming cash rewards are IGNORED
unless they appear via one of these platforms:

1. IssueHunt   — https://issuehunt.io/issues
2. Algora      — https://algora.io/bounties (requires auth)
3. Bountycaster — https://www.bountycaster.xyz (requires auth)

The legacy Immunefi, Code4rena, and Sherlock scrapers are kept for
manual reference but are NOT included in the default SCRAPER_MAP in
pipeline.py. To re-enable them, set the INCLUDE_LEGACY_SCRAPERS env
var to "true".
"""

from .base import BaseScraper, Bounty
from .algora import AlgoraScraper
from .bountycaster import BountycasterScraper
from .issuehunt import IssueHuntScraper

# Legacy scrapers (kept for manual use, NOT in default SCRAPER_MAP)
from .code4rena import Code4renaScraper
from .immunefi import ImmunefiScraper
from .sherlock import SherlockScraper

__all__ = [
    "BaseScraper",
    "Bounty",
    # Verified escrow platforms (default scraping)
    "IssueHuntScraper",
    "AlgoraScraper",
    "BountycasterScraper",
    # Legacy platforms (manual only)
    "ImmunefiScraper",
    "Code4renaScraper",
    "SherlockScraper",
]
