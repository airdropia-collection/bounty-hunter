"""
IssueHunt bounty scraper.

IssueHunt is a platform where GitHub issues have bounties ($2-$500).
Low competition, easy entry point for earning first $.

Data source: https://issuehunt.io/issues
"""
from __future__ import annotations

import re

from src.scrapers.base import BaseScraper, Bounty
from src.utils.logger import get_logger

log = get_logger("scrapers.issuehunt")


class IssueHuntScraper(BaseScraper):
    """Scrapes IssueHunt open bounties."""

    PLATFORM_NAME = "issuehunt"
    BASE_URL = "https://issuehunt.io"
    ISSUES_URL = "https://issuehunt.io/issues"

    def scrape(self) -> list[Bounty]:
        """Scrape IssueHunt bounties."""
        self.log.info("scraping IssueHunt issues page...")
        try:
            html = self._fetch_html(self.ISSUES_URL)
            self.save_raw("issues", html)
            bounties = self._parse_issues(html)
            self.log.info("IssueHunt: found %d bounties", len(bounties))
            return bounties
        except Exception as exc:
            self.log.error("IssueHunt scrape failed: %s", exc)
            return []

    def _parse_issues(self, html: str) -> list[Bounty]:
        """Parse IssueHunt bounty data from HTML."""
        bounties: list[Bounty] = []

        # IssueHunt has links like: /r/owner/repo/issues/123
        issue_links = re.findall(r'href="(/r/[^/]+/[^/]+/issues/\d+)"', html)

        # Find bounty amounts: $2.00, $20.00, $5.00 etc.
        amounts = re.findall(r'\$([0-9,.]+)', html)

        # Deduplicate links
        seen = set()
        unique_links = []
        for link in issue_links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)

        self.log.debug("raw: %d links, %d amounts", len(unique_links), len(amounts))

        for i, link in enumerate(unique_links[:50]):  # Top 50
            # Parse repo and issue number from link
            # /r/owner/repo/issues/123
            match = re.match(r'/r/([^/]+)/([^/]+)/issues/(\d+)', link)
            if not match:
                continue

            owner, repo, issue_num = match.group(1), match.group(2), match.group(3)

            # Get amount if available
            amount = 0
            if i < len(amounts):
                try:
                    amount = int(float(amounts[i]))
                except ValueError:
                    pass

            # GitHub source URL
            github_url = f"https://github.com/{owner}/{repo}/issues/{issue_num}"

            bounty = Bounty(
                id=f"issuehunt-{owner}-{repo}-{issue_num}",
                platform=self.PLATFORM_NAME,
                project_name=f"{owner}/{repo}#{issue_num}",
                description=f"IssueHunt bounty for {owner}/{repo} issue #{issue_num}. Reward: ${amount}",
                max_payout_usd=amount,
                severity_levels=["Low", "Medium"],
                tech_stack=["GitHub", "Open Source"],
                source_urls=[github_url],
                url=f"{self.BASE_URL}{link}",
                deadline=None,
                status="active",
                tags=["github-issue", "bounty", "low-competition"] + (["small"] if amount <= 100 else []),
            )
            bounties.append(bounty)

        return bounties
