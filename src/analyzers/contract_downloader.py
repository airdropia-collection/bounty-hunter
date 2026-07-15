"""
Contract source code downloader.

Fetches Solidity source code from:
1. GitHub repos (for Code4rana/Sherlock audit contests)
2. Etherscan (for Immunefi bug bounties — by contract address)

Caches downloads to avoid re-fetching.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from src.utils.logger import get_logger
from src.utils.retry import retry_network

log = get_logger("contract_downloader")

CACHE_DIR = Path("cache/contracts")


class ContractDownloader:
    """Downloads Solidity source code from GitHub or Etherscan."""

    def __init__(self, etherscan_api_key: str | None = None):
        self.etherscan_key = etherscan_api_key or os.getenv("ETHERSCAN_API_KEY", "")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def download(self, source_url: str) -> str | None:
        """Download contract source. Returns source code or None."""
        # Check cache first
        cache_key = self._cache_key(source_url)
        cache_path = CACHE_DIR / f"{cache_key}.sol"
        if cache_path.exists():
            log.debug("cache hit: %s", cache_path)
            return cache_path.read_text(encoding="utf-8")

        # Determine source type
        if "github.com" in source_url:
            source = self._download_github(source_url)
        elif source_url.startswith("0x") and len(source_url) == 42:
            source = self._download_etherscan(source_url)
        elif "etherscan" in source_url:
            # Extract address from Etherscan URL
            addr_match = re.search(r"0x[a-fA-F0-9]{40}", source_url)
            if addr_match:
                source = self._download_etherscan(addr_match.group())
            else:
                log.warning("could not extract address from %s", source_url)
                return None
        else:
            log.warning("unknown source type: %s", source_url)
            return None

        if source:
            cache_path.write_text(source, encoding="utf-8")
            log.info("downloaded %d chars from %s", len(source), source_url)

        return source

    @retry_network(max_attempts=2, base_delay=1.0, max_delay=5.0)
    def _download_github(self, url: str) -> str | None:
        """Download from GitHub repo. Returns concatenated .sol files."""
        import httpx

        # Parse GitHub URL: https://github.com/owner/repo
        match = re.match(r"https://github\.com/([^/]+)/([^/]+)", url)
        if not match:
            log.warning("could not parse GitHub URL: %s", url)
            return None

        owner, repo = match.group(1), match.group(2)
        # Remove .git suffix if present
        repo = repo.replace(".git", "")

        # Use GitHub API to get repo tree
        api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/main?recursive=1"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "bounty-hunter",
        }
        # Add auth if GH_PAT is available
        gh_pat = os.getenv("GH_PAT", "")
        if gh_pat:
            headers["Authorization"] = f"Bearer {gh_pat}"

        resp = httpx.get(api_url, headers=headers, timeout=30)
        if resp.status_code == 404:
            # Try 'master' branch instead of 'main'
            api_url = api_url.replace("/main?", "/master?")
            resp = httpx.get(api_url, headers=headers, timeout=30)

        if resp.status_code != 200:
            log.warning("GitHub API %d for %s", resp.status_code, api_url)
            return None

        tree = resp.json().get("tree", [])
        sol_files = [
            f for f in tree
            if f.get("path", "").endswith(".sol")
            and "test" not in f.get("path", "").lower()
            and "mock" not in f.get("path", "").lower()
        ][:10]  # Limit to first 10 .sol files

        if not sol_files:
            log.info("no .sol files found in %s/%s", owner, repo)
            return None

        # Download each file
        sources = []
        for f in sol_files:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{f['path']}"
            try:
                file_resp = httpx.get(raw_url, headers={"User-Agent": "bounty-hunter"}, timeout=15)
                if file_resp.status_code == 200:
                    sources.append(f"// File: {f['path']}\n{file_resp.text}")
            except Exception as exc:
                log.debug("failed to fetch %s: %s", f["path"], exc)

        return "\n\n".join(sources) if sources else None

    @retry_network(max_attempts=2, base_delay=1.0, max_delay=5.0)
    def _download_etherscan(self, address: str) -> str | None:
        """Download verified contract source from Etherscan."""
        if not self.etherscan_key:
            log.warning("no ETHERSCAN_API_KEY — can't fetch contract source")
            return None

        import httpx

        url = "https://api.etherscan.io/api"
        params = {
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
            "apikey": self.etherscan_key,
        }
        resp = httpx.get(url, params=params, timeout=30)
        data = resp.json()

        if data.get("status") != "1":
            log.warning("Etherscan API error: %s", data.get("message", "unknown"))
            return None

        result = data.get("result", [])
        if not result:
            return None

        source_code = result[0].get("SourceCode", "")
        if not source_code:
            log.info("contract %s is not verified on Etherscan", address)
            return None

        return source_code

    @staticmethod
    def _cache_key(url: str) -> str:
        """Generate cache key from URL."""
        # Use last part of URL, sanitized
        key = url.replace("https://", "").replace("http://", "")
        key = re.sub(r"[^a-zA-Z0-9]", "_", key)
        return key[:100]  # Limit length
