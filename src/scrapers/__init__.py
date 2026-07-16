"""Platform scrapers for bug bounty listings.

VERIFIED-PLATFORMS-ONLY POLICY (per user directive 2026-07-16,
updated 2026-07-17):

The bot ONLY scrapes bounty listings from these two verified escrow
platforms. Random GitHub issues claiming cash rewards are IGNORED
unless they appear via one of these platforms:

1. IssueHunt    — https://issuehunt.io/issues (public, no auth)
2. Bountycaster — https://www.bountycaster.xyz (requires NEYNAR_API_KEY
                  or BOUNTYCASTER_AUTH_COOKIE)

⚠️ Algora was REMOVED on 2026-07-17 because the platform has pivoted
from a public bounty board to a recruiting marketplace. Its scraper
module was dead weight and has been deleted. Do NOT re-add Algora
unless it relaunches a public bounty board.

The legacy Immunefi, Code4rena, and Sherlock scrapers are kept for
manual reference but are NOT included in the default SCRAPER_MAP in
pipeline.py. To re-enable them, set the INCLUDE_LEGACY_SCRAPERS env
var to "true".
"""

from .base import BaseScraper, Bounty
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
    "BountycasterScraper",
    # Legacy platforms (manual only)
    "ImmunefiScraper",
    "Code4renaScraper",
    "SherlockScraper",
]
