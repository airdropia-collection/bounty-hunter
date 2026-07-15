"""
Sherlock audit contest scraper.

Sherlock hosts competitive smart contract audits similar to Code4rana.
Prize pools range from $5k to $30k. Contests last 7-14 days.

Data source: https://www.sherlock.xyz/audits
"""
from __future__ import annotations

import re
from typing import List

from src.scrapers.base import BaseScraper, Bounty
from src.utils.logger import get_logger

log = get_logger("scrapers.sherlock")


class SherlockScraper(BaseScraper):
    """Scrapes Sherlock audit contests."""

    PLATFORM_NAME = "sherlock"
    BASE_URL = "https://www.sherlock.xyz"
    AUDITS_URL = "https://www.sherlock.xyz/audits"

    def scrape(self) -> List[Bounty]:
        """Scrape Sherlock contests."""
        self.log.info("scraping Sherlock audits page...")
        try:
            html = self._fetch_html(self.AUDITS_URL)
            self.save_raw("audits", html)
            bounties = self._parse_contests(html)
            self.log.info("Sherlock: found %d contests", len(bounties))
            return bounties
        except Exception as exc:
            self.log.error("Sherlock scrape failed: %s", exc)
            return []

    def _parse_contests(self, html: str) -> List[Bounty]:
        """Parse Sherlock contest data from HTML.

        Sherlock's page structure varies — we try multiple patterns
        to extract contest name, prize pool, and repo URL.
        """
        bounties: List[Bounty] = []

        # Sherlock uses Next.js or similar SSR
        # Try to find contest entries
        # Pattern 1: Look for links to /audits/<contest-slug>
        contest_links = re.findall(r'href="/audits/([^"/]+)"', html)

        # Pattern 2: Look for prize amounts ($X,XXX or $XXk)
        prizes = re.findall(r'\$([0-9,]+)\s*(?:USD|USDC)?', html)

        # Pattern 3: Look for GitHub repo links
        repos = re.findall(r'github\.com/([^/\s"\\]+/[^/\s"\\]+)', html)

        # Deduplicate contest links
        seen_slugs = set()
        for slug in contest_links:
            if slug in seen_slugs or slug in ("protocol", "report"):
                continue
            seen_slugs.add(slug)

            # Format slug as project name
            project_name = slug.replace("-", " ").replace("_", " ").title()

            bounty = Bounty(
                id=f"sherlock-{slug}",
                platform=self.PLATFORM_NAME,
                project_name=project_name,
                description=f"Sherlock audit contest: {project_name}",
                max_payout_usd=0,  # Will be enriched later if prize data found
                severity_levels=["High", "Medium", "Low"],
                tech_stack=["Solidity"],
                source_urls=[],
                url=f"{self.BASE_URL}/audits/{slug}",
                deadline=None,
                status="active",
                tags=["audit-contest", "web3"],
            )
            bounties.append(bounty)

        # If we found prize data, assign to bounties (best-effort matching)
        for i, bounty in enumerate(bounties):
            if i < len(prizes) and bounty.max_payout_usd == 0:
                try:
                    bounty.max_payout_usd = int(prizes[i].replace(",", ""))
                except ValueError:
                    pass

        return bounties
