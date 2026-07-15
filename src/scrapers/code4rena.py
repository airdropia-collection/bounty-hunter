"""
Code4rena audit contest scraper.

Code4rana hosts competitive smart contract audits where multiple
security researchers compete for a prize pool. Contests typically
last 7-14 days with prize pools of $2k-$50k.

Data source: https://code4rena.com/contests (Next.js SSR page)
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
            self.log.error("Code4rana scrape failed: %s", exc)
            return []

    def _parse_contests(self, html: str) -> List[Bounty]:
        """Parse Code4rana contest data from HTML.

        Code4rana embeds contest data in Next.js __NEXT_DATA__.
        We look for: title, slug, prize pool, start/end dates, repo URL.
        """
        bounties: List[Bounty] = []

        # Code4rana uses Next.js — data in __NEXT_DATA__ script
        # Try to find contest objects
        # Pattern: {"title":"...","slug":"...","amount":"$X USD",...}

        # Extract titles
        titles = re.findall(r'\\"title\\":\\"([^\\]+)\\"', html)
        # Extract slugs
        slugs = re.findall(r'\\"slug\\":\\"([^\\]+)\\"', html)
        # Extract prize amounts (format: "$25,000 USD" or "$2k USDC")
        prizes = re.findall(r'\\"amount\\":\\"\\\$([0-9,]+)\s*USD\\"', html)
        # Extract repo URLs
        repos = re.findall(r'\\"repo\\":\\"([^\\]+)\\"', html)

        count = min(len(titles), len(slugs))
        self.log.debug(
            "raw fields: titles=%d, slugs=%d, prizes=%d, repos=%d",
            len(titles), len(slugs), len(prizes), len(repos),
        )

        for i in range(count):
            title = titles[i]
            slug = slugs[i]

            # Parse prize amount
            max_payout = 0
            if i < len(prizes):
                prize_str = prizes[i].replace(",", "")
                try:
                    max_payout = int(prize_str)
                except ValueError:
                    pass

            # Parse repo URL
            source_urls: List[str] = []
            if i < len(repos) and repos[i]:
                repo = repos[i]
                if not repo.startswith("http"):
                    repo = f"https://github.com/{repo}"
                source_urls.append(repo)

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
