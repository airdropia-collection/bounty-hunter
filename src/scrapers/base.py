"""
Base scraper class and Bounty dataclass.

Every platform scraper inherits from BaseScraper and implements
``scrape()`` to return a list of Bounty objects.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger
from src.utils.retry import retry_network

log = get_logger("scrapers.base")


@dataclass
class Bounty:
    """A scraped bounty listing from any platform."""
    id: str                           # platform-native ID (e.g., "immunefi-aave-v3")
    platform: str                     # "immunefi" | "code4rana" | "sherlock" | "gitcoin"
    project_name: str
    description: str
    max_payout_usd: int               # highest tier payout in USD
    severity_levels: List[str]        # ["critical", "high", ...]
    tech_stack: List[str]             # ["solidity", "foundry", ...]
    source_urls: List[str]            # GitHub repos / contract addresses
    url: str                          # bounty listing URL
    deadline: Optional[str] = None    # ISO date or None
    status: str = "active"            # "active" | "ending_soon" | "ended"
    tags: List[str] = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def dedup_key(self) -> str:
        """Unique key for dedup state."""
        return f"{self.platform}:{self.id}"


class BaseScraper(ABC):
    """Abstract base class for all platform scrapers."""

    # Subclass must set these
    PLATFORM_NAME: str = ""
    BASE_URL: str = ""

    def __init__(self):
        self.log = get_logger(f"scrapers.{self.PLATFORM_NAME}")

    @abstractmethod
    def scrape(self) -> List[Bounty]:
        """Scrape bounties from the platform. Returns list of Bounty objects."""
        pass

    # ------------------------------------------------------------------ #
    # HTTP helper (sync, with retry)
    # ------------------------------------------------------------------ #
    @retry_network(max_attempts=3, base_delay=1.0, max_delay=5.0)
    def _fetch_html(self, url: str, headers: Optional[Dict] = None) -> str:
        """Fetch HTML from URL with retry. Returns empty string on failure."""
        import httpx

        default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            default_headers.update(headers)

        resp = httpx.get(url, headers=default_headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.text

    @retry_network(max_attempts=3, base_delay=1.0, max_delay=5.0)
    def _fetch_json(self, url: str, headers: Optional[Dict] = None) -> Any:
        """Fetch JSON from URL with retry."""
        import httpx

        default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }
        if headers:
            default_headers.update(headers)

        resp = httpx.get(url, headers=default_headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------ #
    # Output helpers
    # ------------------------------------------------------------------ #
    def save_raw(self, name: str, data: str) -> Path:
        """Save raw HTML/JSON to cache/ for debugging + test fixtures."""
        cache_dir = Path("cache") / self.PLATFORM_NAME
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{name}.html"
        path.write_text(data, encoding="utf-8")
        self.log.debug("saved raw HTML to %s", path)
        return path

    def save_bounties(self, bounties: List[Bounty]) -> Path:
        """Save scraped bounties to state/bounties_<platform>.json."""
        state_dir = Path("state")
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / f"bounties_{self.PLATFORM_NAME}.json"
        data = [b.to_dict() for b in bounties]
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        self.log.info("saved %d bounties to %s", len(bounties), path)
        return path
