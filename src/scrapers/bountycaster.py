"""
Bountycaster Hub bounty scraper.

⚠️ IMPORTANT — READ BEFORE USING:
Bountycaster (https://www.bountycaster.xyz) is a Farcaster-native bounty
platform. As of 2026-07, the public `/api/v1/bounties/open` endpoint
requires Privy/Farcaster authentication — anonymous requests return
`{"bounties":[]}` even when 2,967+ bounties exist on the platform.

This scraper supports three data sources, tried in order:

1. BOUNTYCASTER_AUTH_COOKIE env var → uses a logged-in browser session
   cookie to call `/api/v1/bounties/open`. Get the cookie by logging in
   via Warpcast / Farcaster at https://www.bountycaster.xyz, then copy
   the `privy-session` (or full Cookie header) from DevTools.

2. NEYNAR_API_KEY env var → calls Neynar's official Farcaster API to
   fetch casts under the Bountycaster parent URL. Free tier: 1000
   req/day. Register at https://neynar.com.

3. Public endpoint (no auth) → tries the unauthenticated API as a
   last resort (currently returns empty, but if Bountycaster ever opens
   up, this path picks it up automatically).

If all sources fail, returns [] and logs a 🛡️ FILTER event.

Verified platform status (agent.md §3 "verified escrow platforms"):
- ✅ Bountycaster is on the verified escrow list
- ⚠️ Requires auth cookie or Neynar API key to scrape (no anon access)
- 💰 $1.5M+ in bounties posted, 2,967+ total bounties as of 2026-07
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, List

from src.scrapers.base import BaseScraper, Bounty
from src.utils.logger import get_logger

log = get_logger("scrapers.bountycaster")


class BountycasterScraper(BaseScraper):
    """Scrapes Bountycaster.xyz bounties.

    Bountycaster bounties are Farcaster casts with structured bounty
    metadata. Each bounty has: title, description, reward (USD or token),
    deadline, sponsor FID, and status (open/in-progress/completed/expired).
    """

    PLATFORM_NAME = "bountycaster"
    BASE_URL = "https://www.bountycaster.xyz"
    # Discovered API endpoint (from client-side JS RSC payload)
    API_OPEN_BOUNTIES = "https://www.bountycaster.xyz/api/v1/bounties/open"
    # Bountycaster's Farcaster parent URL (used for Neynar lookups)
    FARCASTER_PARENT_URL = "https://www.bountycaster.xyz"

    # Neynar API (official Farcaster indexer)
    NEYNAR_BASE = "https://api.neynar.com/v2/farcaster"

    def scrape(self) -> List[Bounty]:
        """Try every source in order. Returns [] if all blocked."""
        self.log.info("scraping Bountycaster Hub...")

        # Source 1: auth cookie (preferred)
        cookie = os.getenv("BOUNTYCASTER_AUTH_COOKIE", "").strip()
        if cookie:
            self.log.info("trying Bountycaster with auth cookie (len=%d)", len(cookie))
            try:
                bounties = self._scrape_via_cookie(cookie)
                if bounties:
                    self.log.info("Bountycaster cookie scrape: %d bounties", len(bounties))
                    return bounties
                self.log.warning("Bountycaster cookie scrape returned 0 bounties")
            except Exception as exc:  # noqa: BLE001
                self.log.error("Bountycaster cookie scrape error: %s", exc)

        # Source 2: Neynar API (Farcaster indexer)
        neynar_key = os.getenv("NEYNAR_API_KEY", "").strip()
        if neynar_key:
            self.log.info("trying Bountycaster via Neynar API (key len=%d)", len(neynar_key))
            try:
                bounties = self._scrape_via_neynar(neynar_key)
                if bounties:
                    self.log.info("Neynar scrape: %d bounties", len(bounties))
                    return bounties
                self.log.warning("Neynar scrape returned 0 bounties")
            except Exception as exc:  # noqa: BLE001
                self.log.error("Neynar scrape error: %s", exc)

        # Source 3: public API (last resort — usually empty)
        try:
            bounties = self._scrape_via_public_api()
            if bounties:
                self.log.info("Bountycaster public API: %d bounties", len(bounties))
                return bounties
            self.log.info("Bountycaster public API returned 0 bounties (auth required)")
        except Exception as exc:  # noqa: BLE001
            self.log.debug("Bountycaster public API error: %s", exc)

        # All sources failed — notify operator
        self.log.warning(
            "Bountycaster: all scrape sources failed. "
            "Set BOUNTYCASTER_AUTH_COOKIE or NEYNAR_API_KEY env var to enable."
        )
        self._notify_filter_block()
        return []

    # ------------------------------------------------------------------ #
    # Source 1: Auth cookie → /api/v1/bounties/open
    # ------------------------------------------------------------------ #
    def _scrape_via_cookie(self, cookie: str) -> List[Bounty]:
        """Call /api/v1/bounties/open with a session cookie."""
        headers = {
            "Cookie": cookie if "=" in cookie else f"privy-session={cookie}",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.BASE_URL}/",
            "Origin": self.BASE_URL,
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        data = self._fetch_json(self.API_OPEN_BOUNTIES, headers=headers)
        return self._parse_bountycaster_response(data)

    def _parse_bountycaster_response(self, data: Any) -> List[Bounty]:
        """Parse Bountycaster API response shape:
            {"bounties": [{...bounty fields...}, ...]}
        """
        if not isinstance(data, dict):
            return []
        items = data.get("bounties") or data.get("posts") or []
        if not isinstance(items, list):
            return []

        bounties: List[Bounty] = []
        for item in items:
            try:
                bounty = self._bounty_from_bountycaster_item(item)
                if bounty:
                    bounties.append(bounty)
            except Exception as exc:  # noqa: BLE001
                self.log.debug("skip malformed Bountycaster item: %s", exc)
        return bounties

    def _bounty_from_bountycaster_item(self, item: dict) -> Bounty | None:
        """Convert a Bountycaster bounty dict to a Bounty object.

        Bountycaster bounty fields (observed from page JS):
        - id / hash / castHash
        - title / name
        - description / text / body
        - reward / amount / prize
        - currency (USD, ETH, DAI, USDC, etc.)
        - status (open, in-progress, completed, expired)
        - deadline (ISO date)
        - sponsor / author / user (with fid, username, display_name)
        - url (full bounty URL)
        - tags (list of category tags)
        - network (chain id for crypto rewards)
        """
        bid = str(item.get("id") or item.get("hash") or item.get("castHash") or "")
        if not bid:
            return None

        # Normalize ID — strip 0x prefix for cleanliness
        if bid.startswith("0x"):
            short_id = bid[2:10]
        else:
            short_id = bid[:8] if len(bid) >= 8 else bid

        # Title
        title = (
            item.get("title")
            or item.get("name")
            or (item.get("description", "") or "")[:80]
            or f"bountycaster-{short_id}"
        )

        # Description (combine multiple fields)
        description = (
            item.get("description")
            or item.get("text")
            or item.get("body")
            or item.get("content")
            or ""
        )

        # Reward amount (try every known field name)
        reward = item.get("reward") or item.get("amount") or item.get("prize") or item.get("value")
        currency = (item.get("currency") or item.get("token") or "USD").upper()
        amount_usd = 0
        bounty_value_str = ""

        if isinstance(reward, (int, float)):
            amount_usd = int(reward) if currency in ("USD", "$") else int(reward)
            bounty_value_str = f"{reward} {currency}"
        elif isinstance(reward, str):
            # Parse strings like "$50", "100 USDC", "0.5 ETH"
            m = re.search(r"([\d.]+)\s*([A-Za-z\$]+)?", reward.replace(",", ""))
            if m:
                try:
                    val = float(m.group(1))
                    cur = (m.group(2) or currency or "USD").upper().lstrip("$")
                    if cur in ("USD", "$"):
                        amount_usd = int(val)
                    else:
                        amount_usd = int(val)  # crypto amount, no USD conversion
                    bounty_value_str = f"{val} {cur}"
                except ValueError:
                    pass

        # Source URLs — try to find a GitHub repo link in the description
        source_urls = []
        for url_field in ("repo_url", "issue_url", "github_url", "link"):
            if item.get(url_field):
                source_urls.append(item[url_field])
        # Also extract from description
        if description:
            github_urls = re.findall(
                r"https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(?:/issues/\d+)?",
                description,
            )
            for url in github_urls[:3]:  # cap to 3
                if url not in source_urls:
                    source_urls.append(url)

        # Project name — prefer GitHub repo, fall back to title
        project_name = title[:80]
        for url in source_urls:
            m = re.match(r"https?://github\.com/([^/]+/[^/]+)", url)
            if m:
                project_name = m.group(1)
                break

        # Sponsor info
        sponsor = item.get("sponsor") or item.get("author") or item.get("user") or {}
        if isinstance(sponsor, dict):
            sponsor_name = sponsor.get("username") or sponsor.get("display_name") or "unknown"
        else:
            sponsor_name = str(sponsor)

        # Tech stack — guess from tags + description
        tech_stack: list[str] = []
        tags_raw = item.get("tags") or []
        if isinstance(tags_raw, list):
            tech_stack = [str(t) for t in tags_raw][:5]
        # Add language hints from description
        desc_lower = description.lower()
        for lang in ["solidity", "rust", "typescript", "javascript", "python", "go", "elixir", "react"]:
            if lang in desc_lower and lang not in tech_stack:
                tech_stack.append(lang)

        # Bounty URL
        bounty_url = item.get("url") or f"{self.BASE_URL}/bounty/{bid}"

        # Deadline
        deadline = item.get("deadline") or item.get("expires_at")

        # Status
        status_raw = (item.get("status") or "open").lower()
        if status_raw == "open":
            status = "active"
        elif status_raw == "in-progress":
            status = "active"
        elif status_raw in ("completed", "expired"):
            status = "ended"
        else:
            status = "active"

        return Bounty(
            id=f"bountycaster-{bid}",
            platform=self.PLATFORM_NAME,
            project_name=project_name,
            description=(description[:500] if description else f"Bountycaster bounty: {title}"),
            max_payout_usd=amount_usd,
            severity_levels=["Medium"],  # Bountycaster doesn't use severity
            tech_stack=tech_stack or ["unknown"],
            source_urls=source_urls,
            url=bounty_url,
            deadline=deadline,
            status=status,
            tags=[
                "bountycaster",
                "verified-escrow",
                "farcaster",
                f"sponsor:{sponsor_name}",
            ] + ([bounty_value_str] if bounty_value_str else []),
        )

    # ------------------------------------------------------------------ #
    # Source 2: Neynar API (Farcaster indexer)
    # ------------------------------------------------------------------ #
    def _scrape_via_neynar(self, api_key: str) -> List[Bounty]:
        """Fetch Bountycaster casts via Neynar's feed API.

        Neynar endpoint: /v2/farcaster/feed/?feed_type=filter&filter_type=parent_url
        Returns casts that are replies to a given parent URL.
        """
        # Build URL — filter casts whose parent_url is bountycaster.xyz
        from urllib.parse import urlencode
        params = urlencode({
            "feed_type": "filter",
            "filter_type": "parent_url",
            "parent_url": self.FARCASTER_PARENT_URL,
            "limit": 100,
        })
        url = f"{self.NEYNAR_BASE}/feed/?{params}"
        headers = {
            "api_key": api_key,
            "Accept": "application/json",
            "User-Agent": "bounty-hunter-bot/1.0",
        }
        data = self._fetch_json(url, headers=headers)
        return self._parse_neynar_response(data)

    def _parse_neynar_response(self, data: Any) -> List[Bounty]:
        """Parse Neynar feed response into Bounty objects.

        Neynar feed shape:
            {"casts": [{"hash": "0x...", "text": "...", "author": {...}, ...}, ...]}
        """
        if not isinstance(data, dict):
            return []
        casts = data.get("casts") or []
        if not isinstance(casts, list):
            return []

        bounties: List[Bounty] = []
        for cast in casts:
            try:
                bounty = self._bounty_from_cast(cast)
                if bounty:
                    bounties.append(bounty)
            except Exception as exc:  # noqa: BLE001
                self.log.debug("skip Neynar cast: %s", exc)
        return bounties

    def _bounty_from_cast(self, cast: dict) -> Bounty | None:
        """Convert a Farcaster cast (from Neynar) to a Bounty object.

        Bountycaster bounties are casts with structured text. We extract:
        - title (first line of cast text, up to ~80 chars)
        - reward (search for $X or X USD/ETH/USDC patterns)
        - deadline (search for "deadline:" or ISO date pattern)
        - GitHub URLs from cast text
        """
        cast_hash = cast.get("hash") or ""
        if not cast_hash:
            return None

        text = cast.get("text") or ""
        if not text:
            return None

        # Bountycaster casts usually have a reward mentioned
        # Skip if no $ or token amount in text
        if not re.search(r"[\$]\s*\d|USDC|ETH|DAI|\b\d+\s+(?:USD|USDC|ETH|DAI)\b", text, re.IGNORECASE):
            return None

        # Title = first non-empty line, max 80 chars
        title = ""
        for line in text.split("\n"):
            line = line.strip()
            if line and not line.startswith("http"):
                title = line[:80]
                break
        if not title:
            title = f"bountycaster-{cast_hash[2:10] if cast_hash.startswith('0x') else cast_hash[:8]}"

        # Extract reward
        amount_usd = 0
        bounty_value_str = ""
        m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", text)
        if m:
            try:
                amount_usd = int(float(m.group(1).replace(",", "")))
                bounty_value_str = f"${amount_usd}"
            except ValueError:
                pass
        if not amount_usd:
            m = re.search(r"(\d+(?:\.\d+)?)\s+(USDC|ETH|DAI|USD)", text, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1))
                    cur = m.group(2).upper()
                    amount_usd = int(val)
                    bounty_value_str = f"{val} {cur}"
                except ValueError:
                    pass

        # Extract GitHub URLs
        source_urls = re.findall(
            r"https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(?:/issues/\d+)?",
            text,
        )

        # Project name
        project_name = title[:80]
        for url in source_urls:
            m = re.match(r"https?://github\.com/([^/]+/[^/]+)", url)
            if m:
                project_name = m.group(1)
                break

        # Author
        author = cast.get("author") or {}
        sponsor_name = author.get("username") or "unknown"

        # Cast URL
        cast_url = f"https://warpcast.com/{sponsor_name}/{cast_hash}"

        return Bounty(
            id=f"bountycaster-{cast_hash}",
            platform=self.PLATFORM_NAME,
            project_name=project_name,
            description=text[:500],
            max_payout_usd=amount_usd,
            severity_levels=["Medium"],
            tech_stack=["farcaster", "bountycaster"],
            source_urls=source_urls,
            url=cast_url,
            deadline=None,
            status="active",
            tags=[
                "bountycaster",
                "verified-escrow",
                "farcaster",
                "neynar-source",
                f"sponsor:{sponsor_name}",
            ] + ([bounty_value_str] if bounty_value_str else []),
        )

    # ------------------------------------------------------------------ #
    # Source 3: Public API (no auth — usually empty)
    # ------------------------------------------------------------------ #
    def _scrape_via_public_api(self) -> List[Bounty]:
        """Call /api/v1/bounties/open without auth. Usually returns []."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.BASE_URL}/",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        data = self._fetch_json(self.API_OPEN_BOUNTIES, headers=headers)
        return self._parse_bountycaster_response(data)

    # ------------------------------------------------------------------ #
    # Operator notification when blocked
    # ------------------------------------------------------------------ #
    def _notify_filter_block(self) -> None:
        """Send a 🛡️ FILTER Telegram event so the operator knows
        Bountycaster scraping is blocked (needs credentials)."""
        try:
            from src.utils.telegram import get_notifier
            from src.utils import state_manager
            state_manager.update_pointer(
                stage="SCRAPING_BLOCKED",
                last_action="Bountycaster scraper blocked — no auth cookie or Neynar API key",
                current_target_repo="bountycaster.xyz",
            )
            tg = get_notifier()
            tg.send_filter_event(
                repo="bountycaster.xyz",
                reason="Bountycaster requires auth (Privy/Farcaster)",
                details=(
                    "Set BOUNTYCASTER_AUTH_COOKIE or NEYNAR_API_KEY GitHub Secret. "
                    "Until then, Bountycaster scraping is skipped."
                ),
            )
        except Exception:  # noqa: BLE001
            pass  # notifications are best-effort
