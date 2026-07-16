"""
Algora Dev Board bounty scraper.

⚠️ IMPORTANT — READ BEFORE USING:
Algora (https://algora.io) has pivoted from a public bounty board to a
recruiting marketplace. As of 2026-07, the public `/bounties` route
redirects to `/auth/login` for unauthenticated users.

This scraper supports three data sources, tried in order:

1. ALGORA_API_KEY env var → calls Algora's authenticated API
   (https://algora.io/api/bounties with `Authorization: Bearer <key>`).
   Register for an API key at https://algora.io/settings/api-keys.

2. ALGORA_SESSION_COOKIE env var → uses a logged-in browser session
   cookie (`_algora_key=...`) to fetch the LiveView HTML and parse the
   embedded initial state. Refresh the cookie by logging in via browser
   and copying from DevTools → Application → Cookies.

3. Public RSS/JSON feed (no auth) → if Algora ever publishes a public
   feed again, this path picks it up automatically.

If none of the above yield data, the scraper returns an empty list and
logs a 🛡️ FILTER event to Telegram so the operator knows to refresh
credentials.

Verified platform status (agent.md §3 "verified escrow platforms"):
- ✅ Algora is on the verified escrow list
- ⚠️ Requires API key or session cookie to scrape (no anon access)
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, List

from src.scrapers.base import BaseScraper, Bounty
from src.utils.logger import get_logger

log = get_logger("scrapers.algora")


class AlgoraScraper(BaseScraper):
    """Scrapes Algora Dev Board bounties.

    Tries authenticated API first, then session-cookie HTML scrape,
    then any public feed. Returns [] gracefully if all sources fail.
    """

    PLATFORM_NAME = "algora"
    BASE_URL = "https://algora.io"
    BOUNTIES_URL = "https://algora.io/bounties"
    API_URL = "https://algora.io/api/bounties"

    def scrape(self) -> List[Bounty]:
        """Try every source in order. Returns [] if all blocked."""
        self.log.info("scraping Algora Dev Board...")

        # Source 1: authenticated API (preferred)
        api_key = os.getenv("ALGORA_API_KEY", "").strip()
        if api_key:
            self.log.info("trying Algora authenticated API (key len=%d)", len(api_key))
            try:
                bounties = self._scrape_via_api(api_key)
                if bounties:
                    self.log.info("Algora API: %d bounties", len(bounties))
                    return bounties
                self.log.warning("Algora API returned 0 bounties (key may be invalid)")
            except Exception as exc:  # noqa: BLE001
                self.log.error("Algora API error: %s", exc)

        # Source 2: session cookie (LiveView HTML scrape)
        cookie = os.getenv("ALGORA_SESSION_COOKIE", "").strip()
        if cookie:
            self.log.info("trying Algora session-cookie scrape")
            try:
                bounties = self._scrape_via_cookie(cookie)
                if bounties:
                    self.log.info("Algora cookie scrape: %d bounties", len(bounties))
                    return bounties
                self.log.warning("Algora cookie scrape returned 0 bounties")
            except Exception as exc:  # noqa: BLE001
                self.log.error("Algora cookie scrape error: %s", exc)

        # Source 3: public RSS/JSON feed (best-effort, usually empty)
        try:
            bounties = self._scrape_via_public_feed()
            if bounties:
                self.log.info("Algora public feed: %d bounties", len(bounties))
                return bounties
        except Exception as exc:  # noqa: BLE001
            self.log.debug("Algora public feed error (expected): %s", exc)

        # All sources failed — notify operator
        self.log.warning(
            "Algora: all scrape sources failed. "
            "Set ALGORA_API_KEY or ALGORA_SESSION_COOKIE env var to enable."
        )
        self._notify_filter_block()
        return []

    # ------------------------------------------------------------------ #
    # Source 1: Authenticated API
    # ------------------------------------------------------------------ #
    def _scrape_via_api(self, api_key: str) -> List[Bounty]:
        """Call Algora's authenticated JSON API."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "bounty-hunter-bot/1.0",
        }
        data = self._fetch_json(self.API_URL, headers=headers)
        return self._parse_api_response(data)

    def _parse_api_response(self, data: Any) -> List[Bounty]:
        """Parse Algora API JSON response into Bounty objects.

        Algora API shape (best-guess based on Phoenix conventions):
            {
              "data": [
                {
                  "id": "uuid",
                  "title": "...",
                  "description": "...",
                  "amount_cents": 5000,        # $50.00
                  "currency": "USD",
                  "status": "open",
                  "tech_stack": ["elixir", "phoenix"],
                  "repo_url": "https://github.com/owner/repo",
                  "issue_url": "https://github.com/owner/repo/issues/123",
                  "url": "https://algora.io/bounties/<uuid>",
                  "deadline": "2026-07-30T..."
                }, ...
              ]
            }
        """
        if not isinstance(data, dict):
            return []
        items = data.get("data") or data.get("bounties") or []
        if not isinstance(items, list):
            return []

        bounties: List[Bounty] = []
        for item in items:
            try:
                bounty = self._bounty_from_api_item(item)
                if bounty:
                    bounties.append(bounty)
            except Exception as exc:  # noqa: BLE001
                self.log.debug("skip malformed Algora item: %s", exc)
        return bounties

    def _bounty_from_api_item(self, item: dict) -> Bounty | None:
        """Convert one API item to a Bounty object."""
        bid = str(item.get("id") or item.get("uuid") or "")
        if not bid:
            return None
        title = item.get("title") or item.get("name") or "Untitled"
        description = item.get("description") or item.get("body") or ""
        # Amount: try multiple field names
        amount_cents = (
            item.get("amount_cents")
            or item.get("amount_in_cents")
            or item.get("price_cents")
            or 0
        )
        amount_usd = item.get("amount_usd") or item.get("amount")
        if amount_usd is None and amount_cents:
            amount_usd = int(amount_cents) / 100
        amount_usd = int(float(amount_usd or 0))

        source_urls = []
        if item.get("repo_url"):
            source_urls.append(item["repo_url"])
        if item.get("issue_url"):
            source_urls.append(item["issue_url"])
        # Extract owner/repo from issue URL for project_name
        project_name = title
        for url in source_urls:
            m = re.match(r"https?://github\.com/([^/]+/[^/]+)", url)
            if m:
                project_name = m.group(1)
                break

        tech_stack = item.get("tech_stack") or item.get("languages") or []
        if isinstance(tech_stack, str):
            tech_stack = [tech_stack]

        return Bounty(
            id=f"algora-{bid}",
            platform=self.PLATFORM_NAME,
            project_name=project_name,
            description=description[:500] if description else f"Algora bounty: {title}",
            max_payout_usd=amount_usd,
            severity_levels=["Medium"],  # Algora doesn't use severity
            tech_stack=list(tech_stack) or ["unknown"],
            source_urls=source_urls,
            url=item.get("url") or f"{self.BOUNTIES_URL}/{bid}",
            deadline=item.get("deadline"),
            status="active" if item.get("status", "open") == "open" else "ended",
            tags=["algora", "verified-escrow"] + (["bounty"] if amount_usd else []),
        )

    # ------------------------------------------------------------------ #
    # Source 2: Session-cookie LiveView scrape
    # ------------------------------------------------------------------ #
    def _scrape_via_cookie(self, cookie: str) -> List[Bounty]:
        """Fetch the LiveView HTML using a session cookie and parse the
        embedded initial state. The cookie value should be in the format
        `_algora_key=<value>` (the full Cookie header value)."""
        headers = {
            "Cookie": cookie if "=" in cookie else f"_algora_key={cookie}",
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        html = self._fetch_html(self.BOUNTIES_URL, headers=headers)
        self.save_raw("bounties_authed", html)
        return self._parse_liveview_html(html)

    def _parse_liveview_html(self, html: str) -> List[Bounty]:
        """Parse Algora's Phoenix LiveView HTML for embedded bounty data.

        LiveView embeds initial state in <script> tags as JSON or in
        data-phx-* attributes. We look for common patterns:
        - JSON in <script id="bounties-data" type="application/json">
        - data attributes on bounty cards
        - Visible HTML card structure
        """
        bounties: List[Bounty] = []

        # Pattern 1: embedded JSON in script tags
        json_blocks = re.findall(
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        for block in json_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, list):
                    for item in data:
                        b = self._bounty_from_api_item(item)
                        if b:
                            bounties.append(b)
                elif isinstance(data, dict) and "bounties" in data:
                    for item in data["bounties"]:
                        b = self._bounty_from_api_item(item)
                        if b:
                            bounties.append(b)
            except Exception:  # noqa: BLE001
                continue

        if bounties:
            return bounties

        # Pattern 2: parse visible bounty cards (best-effort)
        # Algora bounty cards have links like /bounties/<uuid>
        card_matches = re.findall(
            r'href="(/bounties/[a-f0-9\-]{36})"[^>]*>.*?(\$[\d,]+(?:\.\d+)?)?',
            html,
            re.DOTALL,
        )
        seen_ids: set[str] = set()
        for path, amount_str in card_matches:
            bid = path.rsplit("/", 1)[-1]
            if bid in seen_ids:
                continue
            seen_ids.add(bid)
            amount = 0
            if amount_str:
                try:
                    amount = int(float(amount_str.replace("$", "").replace(",", "")))
                except ValueError:
                    pass
            bounties.append(Bounty(
                id=f"algora-{bid}",
                platform=self.PLATFORM_NAME,
                project_name=f"algora-bounty-{bid[:8]}",
                description=f"Algora bounty (card scrape). Reward: {amount_str or 'unknown'}",
                max_payout_usd=amount,
                severity_levels=["Medium"],
                tech_stack=["unknown"],
                source_urls=[],
                url=f"{self.BASE_URL}{path}",
                deadline=None,
                status="active",
                tags=["algora", "verified-escrow", "card-scrape"],
            ))
        return bounties

    # ------------------------------------------------------------------ #
    # Source 3: Public feed (best-effort)
    # ------------------------------------------------------------------ #
    def _scrape_via_public_feed(self) -> List[Bounty]:
        """Try public RSS/JSON feeds. Usually returns empty."""
        # Try a few common feed paths
        for path in ["/bounties.rss", "/bounties.json", "/feed.xml", "/rss"]:
            try:
                url = f"{self.BASE_URL}{path}"
                if path.endswith(".json"):
                    data = self._fetch_json(url)
                    if isinstance(data, list):
                        return [b for b in (self._bounty_from_api_item(i) for i in data) if b]
                    if isinstance(data, dict) and "bounties" in data:
                        return [b for b in (self._bounty_from_api_item(i) for i in data["bounties"]) if b]
                else:
                    html = self._fetch_html(url)
                    if "<rss" in html or "<feed" in html:
                        return self._parse_rss(xml=html)
            except Exception:  # noqa: BLE001
                continue
        return []

    def _parse_rss(self, xml: str) -> List[Bounty]:
        """Parse RSS/Atom XML for bounty entries."""
        bounties: List[Bounty] = []
        # Very lightweight RSS item parser
        items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
        for item in items:
            title = (re.search(r"<title>(.*?)</title>", item, re.DOTALL) or [None, ""])[1] if re.search(r"<title>(.*?)</title>", item, re.DOTALL) else ""
            link = ""
            m = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
            if m:
                link = m.group(1).strip()
            amount = 0
            m = re.search(r"\$([\d,]+(?:\.\d+)?)", title)
            if m:
                try:
                    amount = int(float(m.group(1).replace(",", "")))
                except ValueError:
                    pass
            if not link:
                continue
            bid = link.rsplit("/", 1)[-1] or title
            bounties.append(Bounty(
                id=f"algora-{bid}",
                platform=self.PLATFORM_NAME,
                project_name=title[:80] or "algora-bounty",
                description=title,
                max_payout_usd=amount,
                severity_levels=["Medium"],
                tech_stack=["unknown"],
                source_urls=[],
                url=link,
                deadline=None,
                status="active",
                tags=["algora", "verified-escrow", "rss"],
            ))
        return bounties

    # ------------------------------------------------------------------ #
    # Operator notification when blocked
    # ------------------------------------------------------------------ #
    def _notify_filter_block(self) -> None:
        """Send a 🛡️ FILTER Telegram event so the operator knows Algora
        scraping is blocked (needs credentials refresh)."""
        try:
            from src.utils.telegram import get_notifier
            from src.utils import state_manager
            # Update execution pointer
            state_manager.update_pointer(
                stage="SCRAPING_BLOCKED",
                last_action="Algora scraper blocked — no API key or session cookie",
                current_target_repo="algora.io/bounties",
            )
            tg = get_notifier()
            tg.send_filter_event(
                repo="algora.io/bounties",
                reason="Algora requires auth (no anon access)",
                details=(
                    "Set ALGORA_API_KEY or ALGORA_SESSION_COOKIE GitHub Secret. "
                    "Until then, Algora scraping is skipped."
                ),
            )
        except Exception:  # noqa: BLE001
            pass  # notifications are best-effort
