"""
Sherlock audit contest + bug bounty scraper.

Sherlock has two programs:
1. Audit contests (competitive, time-limited) at /contests
2. Bug bounties (ongoing) at /bug-bounties/<id>

The /contests page uses React Server Components (RSC) which are harder
to parse. The /bug-bounties page has direct links we can extract.

Data source: https://audits.sherlock.xyz/bug-bounties
"""
from __future__ import annotations

import re

from src.scrapers.base import BaseScraper, Bounty
from src.utils.logger import get_logger

log = get_logger("scrapers.sherlock")


class SherlockScraper(BaseScraper):
    """Scrapes Sherlock bug bounties and audit contests."""

    PLATFORM_NAME = "sherlock"
    BASE_URL = "https://audits.sherlock.xyz"
    BUG_BOUNTIES_URL = "https://audits.sherlock.xyz/bug-bounties"

    def scrape(self) -> list[Bounty]:
        """Scrape Sherlock bug bounties."""
        self.log.info("scraping Sherlock bug-bounties page...")
        try:
            html = self._fetch_html(self.BUG_BOUNTIES_URL)
            self.save_raw("bug-bounties", html)
            bounties = self._parse_bug_bounties(html)
            self.log.info("Sherlock: found %d bug bounties", len(bounties))
            return bounties
        except Exception as exc:
            self.log.error("Sherlock scrape failed: %s", exc)
            return []

    def _parse_bug_bounties(self, html: str) -> list[Bounty]:
        """Parse Sherlock bug bounty data from HTML.

        Sherlock's bug-bounties page lists links to /bug-bounties/<id>.
        Each ID corresponds to a project. We extract the IDs and
        construct bounty URLs.
        """
        bounties: list[Bounty] = []

        # Find all bug-bounty links: href="/bug-bounties/<id>"
        # The ID is usually a number
        bounty_ids = re.findall(r'href="/bug-bounties/(\d+)"', html)
        # Deduplicate
        seen = set()
        unique_ids = []
        for bid in bounty_ids:
            if bid not in seen:
                seen.add(bid)
                unique_ids.append(bid)

        self.log.debug("found %d unique bug-bounty IDs", len(unique_ids))

        for bid in unique_ids[:50]:  # Limit to top 50
            bounty = Bounty(
                id=f"sherlock-bb-{bid}",
                platform=self.PLATFORM_NAME,
                project_name=f"Sherlock Bug Bounty #{bid}",
                description=f"Sherlock ongoing bug bounty (ID: {bid})",
                max_payout_usd=0,  # Unknown without visiting each page
                severity_levels=["Critical", "High", "Medium", "Low"],
                tech_stack=["Solidity"],
                source_urls=[],
                url=f"{self.BASE_URL}/bug-bounties/{bid}",
                deadline=None,
                status="active",
                tags=["bug-bounty", "web3", "sherlock"],
            )
            bounties.append(bounty)

        return bounties
