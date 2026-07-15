"""
Immunefi bug bounty scraper.

Immunefi is the leading Web3 bug bounty platform. Bounties range from
$500 to $10M+ per finding. The explore page at https://immunefi.com/explore/
embeds all bounty data in a Next.js __NEXT_DATA__ script tag.

Data extracted per bounty:
- Project name (e.g., "LayerZero")
- Slug (used for URL: immunefi.com/bounty/layerzero)
- Max payout (USD)
- Technologies (Solidity, Rust, etc.)
- Immunefi Standard compliance
"""
from __future__ import annotations

import re

from src.scrapers.base import BaseScraper, Bounty
from src.utils.logger import get_logger

log = get_logger("scrapers.immunefi")


class ImmunefiScraper(BaseScraper):
    """Scrapes Immunefi bug bounty listings."""

    PLATFORM_NAME = "immunefi"
    BASE_URL = "https://immunefi.com"
    EXPLORE_URL = "https://immunefi.com/explore/"

    def scrape(self) -> list[Bounty]:
        """Scrape all Immunefi bounties from the explore page."""
        self.log.info("scraping Immunefi explore page...")
        try:
            html = self._fetch_html(self.EXPLORE_URL)
            self.save_raw("explore", html)
            bounties = self._parse_bounties(html)
            self.log.info("Immunefi: found %d bounties", len(bounties))
            return bounties
        except Exception as exc:
            self.log.error("Immunefi scrape failed: %s", exc)
            return []

    def _parse_bounties(self, html: str) -> list[Bounty]:
        """Parse bounty data from Immunefi explore page HTML.

        Immunefi uses Next.js SSR. All bounty data is embedded in a
        <script id="__NEXT_DATA__"> tag as JSON. We extract individual
        fields using regex (faster than parsing the full JSON tree).
        """
        bounties: list[Bounty] = []

        # Extract fields using regex on the escaped JSON
        # Immunefi embeds data as: \"project\":\"Name\" with optional whitespace
        # Pattern handles: \"key\": \"value\" or \"key\":\"value\"

        # Find all project names
        projects = re.findall(r'\\"project\\":\s*\\"([^\\]+)\\"', html)
        # Find all slugs
        slugs = re.findall(r'\\"slug\\":\s*\\"([^\\]+)\\"', html)
        # Find all maxBounty values
        maxes = re.findall(r'maxBounty\\":\s*(\d+)', html)

        # Also try to find technologies and launch dates
        # Technologies appear as: \"technologies\":[\"Solidity\",\"Rust\"]
        # but are often empty: \"technologies\":[]
        techs_raw = re.findall(r'\\"technologies\\":\[([^\]]*)\]', html)

        # Find severity levels (Immunefi uses: Critical, High, Medium, Low)
        # These appear per-bounty but pattern varies; default to standard set
        default_severities = ["Critical", "High", "Medium", "Low"]

        count = min(len(projects), len(slugs), len(maxes))
        self.log.debug(
            "raw fields: projects=%d, slugs=%d, maxes=%d, techs=%d",
            len(projects), len(slugs), len(maxes), len(techs_raw),
        )

        for i in range(count):
            project = projects[i]
            slug = slugs[i]
            max_payout = int(maxes[i])

            # Parse technologies if available
            tech_stack: list[str] = []
            if i < len(techs_raw) and techs_raw[i]:
                # Extract technology names from the raw string
                tech_stack = re.findall(r'\\"([^\\]+)\\"', techs_raw[i])

            # Skip if no payout or project name is empty
            if not project or max_payout == 0:
                continue

            bounty = Bounty(
                id=f"immunefi-{slug}",
                platform=self.PLATFORM_NAME,
                project_name=project,
                description=f"Immunefi bug bounty for {project}. Max payout: ${max_payout:,}",
                max_payout_usd=max_payout,
                severity_levels=default_severities,
                tech_stack=tech_stack if tech_stack else ["Solidity"],
                source_urls=[],  # Will be populated in Phase 3 (contract analyzer)
                url=f"{self.BASE_URL}/bounty/{slug}",
                deadline=None,  # Immunefi bounties are ongoing
                status="active",
                tags=["bug-bounty", "web3"] + (["high-value"] if max_payout >= 1_000_000 else []),
            )
            bounties.append(bounty)

        return bounties

    def filter_by_payout(self, bounties: list[Bounty], min_usd: int = 500) -> list[Bounty]:
        """Filter bounties by minimum payout."""
        return [b for b in bounties if b.max_payout_usd >= min_usd]
