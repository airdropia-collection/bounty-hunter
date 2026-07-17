"""
Dework bounty scraper.

⚠️ IMPORTANT — READ BEFORE USING:
Dework (https://dework.xyz) is a Web3 task manager for DAOs and decentralized
organizations. Bounties are tasks within organization workspaces, often paid
in crypto (USDC, ETH, org-native tokens).

This scraper uses Dework's public GraphQL API at https://api.dework.xyz/graphql.

PUBLIC API ACCESS (no auth):
- ✅ getPopularOrganizations → list of ~50+ DAOs with active Dework workspaces
- ✅ getOrganizationBySlug(slug) → org details + workspace list
- ✅ getWorkspace(id) → workspace details

AUTH-REQUIRED API ACCESS:
- ❌ getTasks(input: { ids: [...] }) → task details (needs valid UUIDs)
- ❌ Direct bounty/reward fetching → needs authenticated session

The architecture is fundamentally ID-based: you must know task UUIDs to fetch
them. Public listing of all tasks within a workspace requires authentication.

DATA SOURCES (tried in order):
1. DEWORK_AUTH_TOKEN env var → authenticated GraphQL queries (full access)
   Get this from browser DevTools → Application → Cookies → `auth_token`
   after logging into dework.xyz
2. Public GraphQL API → fetches org + workspace metadata only
3. Web scraping dework.xyz/<org>/<workspace> pages → extracts task titles
   from server-rendered HTML (limited; only first page of tasks visible)

If all sources fail, returns [] and logs a 🛡️ FILTER event.

Verified platform status (agent.md §3):
- ✅ Dework is on the verified escrow platform list (replaced Bountycaster 2026-07-17)
- ⚠️ Public API only returns org/workspace metadata — task data needs auth
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, List
from urllib.parse import urlencode

from src.scrapers.base import BaseScraper, Bounty
from src.utils.logger import get_logger

log = get_logger("scrapers.dework")


class DeworkScraper(BaseScraper):
    """Scrapes Dework.xyz bounties via GraphQL API.

    Strategy:
    1. Fetch popular organizations (public)
    2. For each org, fetch its workspaces (public)
    3. For workspaces named "Bounties" / "Public" / "Contributors":
       a. If DEWORK_AUTH_TOKEN set → fetch tasks via authenticated GraphQL
       b. Otherwise → scrape the workspace's public web page for task titles
    4. Filter for tasks with crypto rewards (USDC, ETH, etc.)
    """

    PLATFORM_NAME = "dework"
    BASE_URL = "https://dework.xyz"
    GRAPHQL_URL = "https://api.dework.xyz/graphql"

    # Workspace name patterns that typically contain bounties
    BOUNTY_WORKSPACE_PATTERNS = re.compile(
        r"bounty|bounties|public|contributor|contributions|reward",
        re.IGNORECASE,
    )

    # Crypto reward patterns to look for in task text
    REWARD_PATTERN = re.compile(
        r"(?:\$|USD|USDC|USDT|ETH|DAI|MATIC|SOL|BTC)\s*[\d,.]+"
        r"|[\d,.]+\s*(?:USD|USDC|USDT|ETH|DAI|MATIC|SOL|BTC)",
        re.IGNORECASE,
    )

    def scrape(self) -> List[Bounty]:
        """Scrape Dework bounties. Returns [] if all sources blocked."""
        self.log.info("scraping Dework...")

        # Source 1: Authenticated GraphQL (preferred)
        auth_token = os.getenv("DEWORK_AUTH_TOKEN", "").strip()
        if auth_token:
            self.log.info("trying Dework authenticated GraphQL (token len=%d)", len(auth_token))
            try:
                bounties = self._scrape_via_authed_graphql(auth_token)
                if bounties:
                    self.log.info("Dework authed GraphQL: %d bounties", len(bounties))
                    return bounties
                self.log.warning("Dework authed GraphQL returned 0 bounties")
            except Exception as exc:  # noqa: BLE001
                self.log.error("Dework authed GraphQL error: %s", exc)

        # Source 2: Public GraphQL + web page scrape (best-effort)
        try:
            bounties = self._scrape_via_public_api()
            if bounties:
                self.log.info("Dework public scrape: %d bounties", len(bounties))
                return bounties
            self.log.info("Dework public scrape returned 0 bounties (auth required for task data)")
        except Exception as exc:  # noqa: BLE001
            self.log.error("Dework public scrape error: %s", exc)

        # All sources failed — notify operator
        self.log.warning(
            "Dework: all scrape sources yielded 0 bounties. "
            "Set DEWORK_AUTH_TOKEN env var to enable task-level scraping. "
            "Without auth, only org/workspace metadata is publicly accessible."
        )
        self._notify_filter_block()
        return []

    # ------------------------------------------------------------------ #
    # GraphQL helpers
    # ------------------------------------------------------------------ #
    def _graphql(self, query: str, variables: dict | None = None, auth_token: str = "") -> dict:
        """Execute a GraphQL query against Dework's API."""
        import httpx

        headers = {
            "Content-Type": "application/json",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = httpx.post(self.GRAPHQL_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            self.log.warning("Dework GraphQL errors: %s", data["errors"][:200])
        return data.get("data", {})

    # ------------------------------------------------------------------ #
    # Source 1: Authenticated GraphQL
    # ------------------------------------------------------------------ #
    def _scrape_via_authed_graphql(self, auth_token: str) -> List[Bounty]:
        """Fetch bounties using an authenticated session.

        Flow:
        1. Get popular organizations
        2. For each org, get workspaces
        3. For each "bounties"-like workspace, get tasks
        4. Filter tasks with rewards
        """
        bounties: List[Bounty] = []

        # Get popular orgs
        data = self._graphql(
            "{ getPopularOrganizations { id name slug } }",
            auth_token=auth_token,
        )
        orgs = data.get("getPopularOrganizations", [])
        self.log.info("Dework: found %d popular orgs", len(orgs))

        # Cap to first 20 orgs to avoid hammering the API
        for org in orgs[:20]:
            org_slug = org.get("slug", "")
            org_name = org.get("name", "")
            if not org_slug:
                continue

            # Get workspaces for this org
            try:
                org_data = self._graphql(
                    'query GetOrg($slug: String!) { getOrganizationBySlug(slug: $slug) '
                    '{ id name slug workspaces { id name slug } } }',
                    variables={"slug": org_slug},
                    auth_token=auth_token,
                )
                workspaces = (
                    org_data.get("getOrganizationBySlug", {}).get("workspaces", [])
                )
            except Exception as exc:  # noqa: BLE001
                self.log.debug("could not fetch workspaces for %s: %s", org_slug, exc)
                continue

            # Filter for bounty-like workspaces
            bounty_workspaces = [
                w for w in workspaces
                if self.BOUNTY_WORKSPACE_PATTERNS.search(w.get("name", ""))
            ]

            for ws in bounty_workspaces[:3]:  # cap to 3 workspaces per org
                ws_id = ws.get("id", "")
                if not ws_id:
                    continue
                try:
                    tasks = self._fetch_tasks_for_workspace(ws_id, auth_token)
                    for task in tasks:
                        bounty = self._bounty_from_task(task, org_name, ws.get("name", ""))
                        if bounty:
                            bounties.append(bounty)
                except Exception as exc:  # noqa: BLE001
                    self.log.debug("could not fetch tasks for workspace %s: %s", ws_id, exc)

            # Cap total bounties per scrape cycle
            if len(bounties) >= 50:
                break

        return bounties[:50]

    def _fetch_tasks_for_workspace(self, workspace_id: str, auth_token: str) -> list[dict]:
        """Fetch tasks for a workspace using authenticated GraphQL.

        Note: Dework's getTasks requires `input: { ids: [...] }` — you must
        already know task UUIDs. Without a "list tasks in workspace" query,
        we use the workspace web page to extract task IDs from the rendered
        HTML, then fetch full details via GraphQL.
        """
        # Try getTasks with workspace-scoped query (if Dework adds it later)
        # Currently this returns empty for unknown IDs
        # TODO: Once Dework exposes a "list tasks by workspace" query, use it here
        # For now, fall back to web page scraping
        return self._scrape_workspace_webpage_for_tasks(workspace_id, auth_token)

    def _scrape_workspace_webpage_for_tasks(self, workspace_id: str, auth_token: str) -> list[dict]:
        """Scrape the workspace's public web page to extract task metadata.

        Dework's SSR pages include task titles + IDs in the HTML even without
        auth (for public workspaces). We extract them and then optionally
        fetch full details via authenticated GraphQL.
        """
        import httpx

        # First, find the workspace's org/slug from its ID
        try:
            ws_data = self._graphql(
                'query GetWs($id: ID!) { getWorkspace(id: $id) { id name slug organization { id name slug } } }',
                variables={"id": workspace_id},
                auth_token=auth_token,
            )
            ws = ws_data.get("getWorkspace", {})
            ws_slug = ws.get("slug", "")
            org_slug = ws.get("organization", {}).get("slug", "")
        except Exception:
            return []

        if not ws_slug or not org_slug:
            return []

        # Fetch the workspace web page
        url = f"{self.BASE_URL}/{org_slug}/{ws_slug}"
        try:
            resp = httpx.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                },
                timeout=30,
                follow_redirects=True,
            )
            html = resp.text
        except Exception as exc:  # noqa: BLE001
            self.log.debug("could not fetch workspace page %s: %s", url, exc)
            return []

        # Extract tasks from __NEXT_DATA__ Apollo cache
        return self._extract_tasks_from_html(html)

    def _extract_tasks_from_html(self, html: str) -> list[dict]:
        """Extract task entries from Dework's SSR HTML.

        Dework embeds Apollo cache state in __NEXT_DATA__ JSON.
        We look for Task: prefixed keys and extract their fields.
        """
        tasks: list[dict] = []
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not m:
            return tasks

        try:
            data = json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            return tasks

        apollo = data.get("props", {}).get("apolloState", {}).get("data", {})
        for key, val in apollo.items():
            if key.startswith("Task:") and isinstance(val, dict):
                tasks.append(val)

        return tasks

    # ------------------------------------------------------------------ #
    # Source 2: Public API (org + workspace metadata only — no tasks)
    # ------------------------------------------------------------------ #
    def _scrape_via_public_api(self) -> List[Bounty]:
        """Fetch what's publicly accessible: popular orgs + their workspaces.

        Without auth, we cannot fetch task-level data. We return an empty
        list but log the orgs + workspaces we discovered so the operator
        knows what's available.
        """
        try:
            data = self._graphql("{ getPopularOrganizations { id name slug } }")
            orgs = data.get("getPopularOrganizations", [])
            self.log.info(
                "Dework public API: found %d orgs (task data requires auth): %s",
                len(orgs),
                ", ".join(o.get("name", "") for o in orgs[:5]),
            )
        except Exception as exc:  # noqa: BLE001
            self.log.error("Dework public API error: %s", exc)

        # Public API cannot return task data — return empty
        return []

    # ------------------------------------------------------------------ #
    # Task → Bounty conversion
    # ------------------------------------------------------------------ #
    def _bounty_from_task(
        self,
        task: dict,
        org_name: str,
        workspace_name: str,
    ) -> Bounty | None:
        """Convert a Dework task dict to a Bounty object.

        Dework Task fields (from schema probing):
        - id (UUID!)
        - name
        - description
        - rewards (plural — array of reward objects)
        - assignees (plural — array of User)
        - creator (User type)
        - status
        """
        task_id = str(task.get("id") or "")
        if not task_id:
            return None

        name = task.get("name") or task.get("title") or "Untitled Dework task"
        description = task.get("description") or ""

        # Extract reward amount from rewards array
        rewards = task.get("rewards") or []
        amount_usd = 0
        bounty_value_str = ""
        if isinstance(rewards, list) and rewards:
            for reward in rewards:
                if not isinstance(reward, dict):
                    continue
                amount = reward.get("amount") or reward.get("value") or 0
                currency = (reward.get("currency") or reward.get("token") or "USD").upper()
                try:
                    amount_num = float(amount)
                    if currency in ("USD", "USDC", "USDT"):
                        amount_usd += int(amount_num)
                    bounty_value_str = f"{amount_num} {currency}"
                except (ValueError, TypeError):
                    pass
        else:
            # Fallback: look for reward pattern in description
            m = self.REWARD_PATTERN.search(description)
            if m:
                bounty_value_str = m.group()
                # Try to parse as USD
                num_match = re.search(r"[\d,.]+", bounty_value_str)
                if num_match:
                    try:
                        amount_usd = int(float(num_match.group().replace(",", "")))
                    except ValueError:
                        pass

        # Extract GitHub URLs from description
        source_urls = []
        if description:
            github_urls = re.findall(
                r"https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(?:/issues/\d+)?",
                description,
            )
            source_urls = github_urls[:3]

        # Project name = org name (Dework bounties are org-scoped)
        project_name = f"{org_name}/{workspace_name}"

        return Bounty(
            id=f"dework-{task_id}",
            platform=self.PLATFORM_NAME,
            project_name=project_name,
            description=(description[:500] if description else f"Dework task: {name}"),
            max_payout_usd=amount_usd,
            severity_levels=["Medium"],  # Dework doesn't use severity
            tech_stack=["web3", "dao"],
            source_urls=source_urls,
            url=f"{self.BASE_URL}/task/{task_id}",
            deadline=task.get("dueDate") or task.get("deadline"),
            status="active" if task.get("status") in (None, "TODO", "IN_PROGRESS") else "ended",
            tags=[
                "dework",
                "verified-escrow",
                "web3",
                f"org:{org_name}",
            ] + ([bounty_value_str] if bounty_value_str else []),
        )

    # ------------------------------------------------------------------ #
    # Operator notification when blocked
    # ------------------------------------------------------------------ #
    def _notify_filter_block(self) -> None:
        """Send a 🛡️ FILTER Telegram event so the operator knows
        Dework scraping is blocked (needs auth token)."""
        try:
            from src.utils.telegram import get_notifier
            from src.utils import state_manager
            state_manager.update_pointer(
                stage="SCRAPING_BLOCKED",
                last_action="Dework scraper returned 0 bounties — task data requires DEWORK_AUTH_TOKEN",
                current_target_repo="dework.xyz",
            )
            tg = get_notifier()
            tg.send_filter_event(
                repo="dework.xyz",
                reason="Dework task data requires auth token",
                details=(
                    "Public GraphQL API returns org + workspace metadata only. "
                    "To fetch actual bounties, set DEWORK_AUTH_TOKEN env var "
                    "(copy `auth_token` cookie from dework.xyz browser session). "
                    "Until then, Dework scraping returns 0 bounties."
                ),
            )
        except Exception:  # noqa: BLE001
            pass  # notifications are best-effort
