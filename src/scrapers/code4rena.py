"""
Code4rena audit contest scraper.

Code4rana hosts competitive smart contract audits where multiple
security researchers compete for a prize pool. Contests typically
last 7-14 days with prize pools of $2k-$50k.

Data source: https://code4rena.com/contests
The page embeds contest data in Next.js __NEXT_DATA__ with escaped
JSON. Fields: title, slug, repo. Prize amounts appear as visible
text ($X,XXX) in the HTML, not in the JSON.
"""
from __future__ import annotations

import re
from typing import List

from src.scrapers.base import BaseScraper, Bounty
from src.utils.logger import get_logger

log = get_logger("scrapers.code4rena")


class Code4renaScraper(BaseScraper):
    """Scrapes Code4rana active contests."""

    PLATFORM_NAME = "code4rena"
    BASE_URL = "https://code4rena.com"
    CONTESTS_URL = "https://code4rena.com/contests"

    def scrape(self) -> List[Bounty]:
        """Scrape Code4rana contests."""
        self.log.info("scraping Code4rana contests page...")
        try:
            html = self._fetch_html(self.CONTESTS_URL)
            self.save_raw("contests", html)
            bounties = self._parse_contests(html)
            self.log.info("Code4rana: found %d contests", len(bounties))
            return bounties
        except Exception as exc:
            self.log.error("Code4rena scrape failed: %s", exc)
            return []

    def _parse_contests(self, html: str) -> List[Bounty]:
        """Parse Code4rana contest data from HTML.

        Code4rena embeds data in Next.js __NEXT_DATA__ with escaped JSON.
        We extract:
        - title (from JSON: \"title\":\"K2\")
        - slug (from JSON: \"slug\":\"2026-04-k2\")
        - repo (from JSON: \"repo\":\"https://github.com/code-423n4/...\")
        - amount (from visible text: $135,000)
        """
        bounties: List[Bounty] = []

        # Extract from escaped JSON
        titles = re.findall(r'\\"title\\":\\"([^\\]+)\\"', html)
        slugs = re.findall(r'\\"slug\\":\\"([^\\]+)\\"', html)
        repos = re.findall(r'\\"repo\\":\\"([^\\]+)\\"', html)

        # Extract prize amounts from visible text: $135,000 or $22,000 USD
        amounts = re.findall(r'\$([0-9,]+)\s*(?:USD|USDC|USDT)?', html)

        count = min(len(titles), len(slugs))
        self.log.debug(
            "raw fields: titles=%d, slugs=%d, repos=%d, amounts=%d",
            len(titles), len(slugs), len(repos), len(amounts),
        )

        for i in range(count):
            title = titles[i]
            slug = slugs[i]

            # Parse prize amount (best-effort matching — amounts are in
            # document order, may not perfectly align with contests)
            max_payout = 0
            if i < len(amounts):
                try:
                    max_payout = int(amounts[i].replace(",", ""))
                except ValueError:
                    pass

            # Parse repo URL
            source_urls: List[str] = []
            if i < len(repos) and repos[i]:
                source_urls.append(repos[i])

            bounty = Bounty(
                id=f"code4rena-{slug}",
                platform=self.PLATFORM_NAME,
                project_name=title,
                description=f"Code4rana audit contest: {title}. Prize pool: ${max_payout:,}",
                max_payout_usd=max_payout,
                severity_levels=["High", "Medium", "Low", "QA", "Gas"],
                tech_stack=["Solidity"],
                source_urls=source_urls,
                url=f"{self.BASE_URL}/contests/{slug}",
                deadline=None,
                status="active",
                tags=["audit-contest", "web3"] + (["high-value"] if max_payout >= 25_000 else []),
            )
            bounties.append(bounty)

        return bounties
