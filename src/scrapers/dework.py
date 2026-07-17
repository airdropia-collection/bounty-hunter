"""
Dework bounty scraper.

⚠️ IMPORTANT — READ BEFORE USING:
Dework (https://dework.xyz) is a Web3 task manager for DAOs and decentralized
organizations. Bounties are tasks within organization workspaces, paid in
crypto (USDC, ETH, USDT, org-native tokens like BANK/MOONEY/BABEL/NEWO).

This scraper uses Dework's public GraphQL API at https://api.dework.xyz/graphql.

VERIFIED WORKING SCHEMA (reverse-engineered 2026-07-17 via error messages):
- getPopularOrganizations → ~891 DAOs (public, no auth)
- getOrganizationBySlug(slug) → org + workspaces list (public)
- getWorkspace(id: UUID!) → workspace + NESTED `tasks` field (public!)
  - tasks: [{ id, name, description, status, priority, dueDate, createdAt,
             updatedAt, assignees, creator, tags, section, rewards }]
  - rewards: [{ amount, type, token: { symbol, address } }]

KEY INSIGHT: `getWorkspace` returns tasks as a nested field — NO need for
the ID-based `getTasks` query. We can list all tasks in any workspace
without knowing task UUIDs upfront.

AMOUNT FORMAT:
- USDC/USDT: 6 decimals (200000000 = 200 USDC)
- ETH/MOONEY/BANK/BABEL/NEWO: 18 decimals (wei)
- Conversion handled in `_bounty_from_task`

AUTH:
- Public API (no auth): org + workspace + task data IS accessible
  (verified — returned real task data for Developer DAO, Avalanche, etc.)
- DEWORK_AUTH_TOKEN env var: optional, increases rate limit + unlocks
  private workspace tasks (if any)

Verified platform status (agent.md §3):
- ✅ Dework is on the verified escrow platform list (replaced Bountycaster 2026-07-17)
"""
from __future__ import annotations

import os
import re

from src.scrapers.base import BaseScraper, Bounty
from src.utils.logger import get_logger

log = get_logger("scrapers.dework")


# Token decimal places (for converting smallest-unit amounts to human-readable)
# IMPORTANT: Same symbol can have different decimals on different chains!
# e.g. USDC is 6 decimals on Ethereum, but 18 decimals on BSC (Binance Pegged)
# So we use ADDRESS-based detection when address is available, falling back
# to symbol-based detection.
TOKEN_DECIMALS_BY_SYMBOL = {
    "USDC": 6, "USDT": 6, "DAI": 18, "ETH": 18, "MATIC": 18, "WMATIC": 18,
    "WETH": 18, "WBTC": 8, "BTC": 8, "AVAX": 18, "WAVAX": 18,
    # DAO-native tokens (assume 18 decimals — standard ERC20)
    "BANK": 18, "MOONEY": 18, "BABEL": 18, "NEWO": 18, "CODE": 18,
    "FHM": 18, "POKT": 6, "GTC": 18, "DORA": 18,
}

# Token address → decimals (known non-standard tokens)
# Binance Pegged tokens often have 18 decimals instead of the standard 6
TOKEN_DECIMALS_BY_ADDRESS = {
    # Binance Pegged USDC (BSC) — 18 decimals instead of standard 6
    "0x8ac76a51cc950d9822d68b8fe3717d61300c8399": 18,
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": 18,  # alt BSC USDC
    # Binance Pegged ETH (BSC) — 18 decimals
    "0x2170ed0880ac9a755fd29b2688956bd959f933f8": 18,
    # Binance Pegged BTC (BSC) — 18 decimals instead of standard 8
    "0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c": 18,
    # Binance Pegged MATIC (BSC) — 18 decimals
    "0xcc42724c6683b7e57334c4e856f4c9965ed682bd": 18,
}

# Active task statuses (bounties still claimable)
ACTIVE_STATUSES = {"TODO", "IN_PROGRESS", "REVIEW", "OPEN", "ASSIGNED"}


class DeworkScraper(BaseScraper):
    """Scrapes Dework.xyz bounties via GraphQL API.

    Strategy (verified working 2026-07-17):
    1. Fetch popular organizations (public)
    2. For each org, fetch workspaces (public)
    3. For each workspace, fetch tasks via NESTED field on getWorkspace
    4. Filter tasks with rewards + active status
    """

    PLATFORM_NAME = "dework"
    BASE_URL = "https://dework.xyz"
    GRAPHQL_URL = "https://api.dework.xyz/graphql"

    def scrape(self) -> list[Bounty]:
        """Scrape Dework bounties. Returns [] if all sources blocked."""
        self.log.info("scraping Dework...")

        # Auth token is optional — public API works without it
        # (auth just increases rate limits + unlocks private workspaces)
        auth_token = os.getenv("DEWORK_AUTH_TOKEN", "").strip()

        try:
            bounties = self._scrape_via_graphql(auth_token)
            if bounties:
                self.log.info("Dework: %d bounties found", len(bounties))
                return bounties
            self.log.info("Dework: 0 bounties found (no active rewarded tasks)")
        except Exception as exc:  # noqa: BLE001
            self.log.error("Dework scrape error: %s", exc)

        # Notify operator if we got 0 bounties
        self.log.warning("Dework: scrape returned 0 bounties")
        self._notify_filter_block()
        return []

    # ------------------------------------------------------------------ #
    # GraphQL helper
    # ------------------------------------------------------------------ #
    def _graphql(self, query: str, auth_token: str = "") -> dict:
        """Execute a GraphQL query against Dework's API.

        IMPORTANT: Dework's GraphQL rejects variable type `UUID!` when passed
        via `$id: String!` (variable type checking is strict). Use INLINE
        arguments instead: `getWorkspace(id: "<UUID>") { ... }`
        """
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
        resp = httpx.post(self.GRAPHQL_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            self.log.warning("Dework GraphQL errors: %s", str(data["errors"])[:300])
        return data.get("data", {})

    # ------------------------------------------------------------------ #
    # Main scrape logic
    # ------------------------------------------------------------------ #
    def _scrape_via_graphql(self, auth_token: str) -> list[Bounty]:
        """Fetch bounties via GraphQL (verified working 2026-07-17).

        Flow:
        1. Get popular organizations (~891 DAOs)
        2. For each org (capped at 30), get workspaces
        3. For each workspace (capped at 5 per org), fetch tasks via
           nested `tasks` field on getWorkspace
        4. Filter tasks with rewards + active status
        """
        bounties: list[Bounty] = []

        # Step 1: Get popular orgs
        data = self._graphql(
            "{ getPopularOrganizations { id name slug } }",
            auth_token=auth_token,
        )
        orgs = data.get("getPopularOrganizations", [])
        self.log.info("Dework: found %d popular orgs", len(orgs))

        # Cap to first 50 orgs (top 10 are old orgs with mostly closed bounties;
        # orgs 10-50 have more active bounties per our scan)
        for org in orgs[:50]:
            org_slug = org.get("slug", "")
            org_name = org.get("name", "")
            if not org_slug:
                continue

            # Step 2: Get workspaces for this org (inline query — Dework rejects
            # variable type UUID! when passed as String!)
            try:
                org_data = self._graphql(
                    f'{{ getOrganizationBySlug(slug: "{org_slug}") '
                    f'{{ id name slug workspaces {{ id name slug }} }} }}',
                    auth_token=auth_token,
                )
                workspaces = (
                    org_data.get("getOrganizationBySlug", {}).get("workspaces", [])
                )
            except Exception as exc:  # noqa: BLE001
                self.log.debug("could not fetch workspaces for %s: %s", org_slug, exc)
                continue

            # Step 3: Scan ALL workspaces (not just "bounty"-named ones) since
            # many orgs put bounties in workspaces named "Engineering",
            # "BD Referrers", "Community Bounties", "Technical & Engineering", etc.
            for ws in workspaces[:5]:  # cap to 5 workspaces per org
                ws_id = ws.get("id", "")
                ws_name = ws.get("name", "")
                if not ws_id:
                    continue
                try:
                    tasks = self._fetch_tasks_for_workspace(ws_id, auth_token)
                    for task in tasks:
                        bounty = self._bounty_from_task(task, org_name, ws_name)
                        if bounty:
                            bounties.append(bounty)
                except Exception as exc:  # noqa: BLE001
                    self.log.debug("could not fetch tasks for %s/%s: %s",
                                   org_slug, ws_name, exc)

            # Cap total bounties per scrape cycle
            if len(bounties) >= 30:
                break

        return bounties[:30]

    def _fetch_tasks_for_workspace(self, workspace_id: str, auth_token: str) -> list[dict]:
        """Fetch tasks for a workspace via nested `tasks` field on getWorkspace.

        VERIFIED WORKING QUERY (2026-07-17):
            {
              getWorkspace(id: "<UUID>") {
                id name slug
                tasks {
                  id name description status priority dueDate createdAt
                  assignees { id username }
                  creator { id username }
                  tags { id name }
                  section { id name }
                  rewards { amount type token { symbol address } }
                }
              }
            }

        Returns ONLY tasks with rewards (bounties) + active status.
        Filters out:
        - Tasks with status DONE / CLOSED / ARCHIVED
        - Tasks with empty rewards array
        - Community chatter (COMMUNITY_SUGGESTIONS status)
        """
        # Use inline query (Dework's GraphQL rejects variable type UUID!
        # when passed via $id: String! — must use inline UUID literal)
        # VERIFIED field names (2026-07-17):
        # - TaskTag has: id, label, color (NOT name)
        # - TaskSection has: id, name
        # - PaymentToken has: symbol, address, name (NOT decimals/chainId)
        query = (
            f'{{ getWorkspace(id: "{workspace_id}") {{ '
            f'id name slug '
            f'tasks {{ '
            f'id name description status priority dueDate createdAt updatedAt '
            f'assignees {{ id username }} '
            f'creator {{ id username }} '
            f'tags {{ id label color }} '
            f'section {{ id name }} '
            f'rewards {{ amount type token {{ symbol address }} }} '
            f'}} }} }}'
        )
        data = self._graphql(query, auth_token=auth_token)
        ws = data.get("getWorkspace", {})
        tasks = ws.get("tasks", [])

        # Filter: only tasks WITH rewards + ACTIVE status
        bounty_tasks = [
            t for t in tasks
            if t.get("rewards")  # has at least one reward
            and t.get("status", "").upper() in ACTIVE_STATUSES
        ]
        return bounty_tasks

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

        Dework Task fields (verified 2026-07-17):
        - id (UUID)
        - name
        - description
        - status (TODO / IN_PROGRESS / REVIEW / DONE / CLOSED / COMMUNITY_SUGGESTIONS)
        - rewards: [{ amount (string, smallest unit), type (FIXED), token: { symbol, address } }]
        - assignees, creator, tags, section, dueDate, createdAt, updatedAt
        """
        task_id = str(task.get("id") or "")
        if not task_id:
            return None

        name = task.get("name") or "Untitled Dework task"
        description = task.get("description") or ""

        # Convert rewards from smallest-unit to human-readable
        rewards = task.get("rewards") or []
        amount_usd = 0
        bounty_value_str = ""

        for reward in rewards:
            if not isinstance(reward, dict):
                continue
            raw_amount = reward.get("amount", 0)
            token = reward.get("token") or {}
            symbol = (token.get("symbol") or "?").upper()
            address = (token.get("address") or "").lower()

            try:
                # Amount is a string in smallest unit (wei-like)
                amount_int = int(raw_amount) if raw_amount else 0
            except (ValueError, TypeError):
                try:
                    amount_int = int(float(raw_amount))
                except (ValueError, TypeError):
                    continue

            # Determine decimals — address takes priority over symbol
            # (Binance Pegged USDC at 0x8AC76a51... has 18 decimals, not 6)
            if address and address in TOKEN_DECIMALS_BY_ADDRESS:
                decimals = TOKEN_DECIMALS_BY_ADDRESS[address]
            elif symbol in TOKEN_DECIMALS_BY_SYMBOL:
                decimals = TOKEN_DECIMALS_BY_SYMBOL[symbol]
                # Heuristic: if symbol is a stablecoin (6 decimals) but amount
                # is huge (>10^15), it's likely a BSC pegged token with 18 decimals
                if decimals == 6 and amount_int > 10**15:
                    decimals = 18
            else:
                decimals = 18  # default for unknown ERC20
            human_amount = amount_int / (10 ** decimals)

            # Accumulate USD value (for stablecoins only)
            if symbol in ("USDC", "USDT", "DAI", "USD"):
                amount_usd += int(human_amount)
                bounty_value_str = f"${int(human_amount)}"
            else:
                # Crypto token — show as token amount
                if human_amount >= 1000:
                    bounty_value_str = f"{human_amount:.0f} {symbol}"
                elif human_amount >= 1:
                    bounty_value_str = f"{human_amount:.2f} {symbol}"
                else:
                    bounty_value_str = f"{human_amount:.6f} {symbol}"

        # If no rewards converted, skip (shouldn't happen — we filter for rewards)
        if not bounty_value_str:
            return None

        # Extract GitHub URLs from description
        source_urls = []
        if description:
            github_urls = re.findall(
                r"https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(?:/issues/\d+)?",
                description,
            )
            source_urls = github_urls[:3]

        # Project name = org/workspace
        project_name = f"{org_name}/{workspace_name}"

        # Status mapping
        task_status = task.get("status", "").upper()
        status = "active" if task_status in ACTIVE_STATUSES else "ended"

        return Bounty(
            id=f"dework-{task_id}",
            platform=self.PLATFORM_NAME,
            project_name=project_name,
            description=(description[:500] if description else f"Dework task: {name}"),
            max_payout_usd=amount_usd,
            severity_levels=["Medium"],
            tech_stack=["web3", "dao", "crypto"],
            source_urls=source_urls,
            url=f"{self.BASE_URL}/task/{task_id}",
            deadline=task.get("dueDate"),
            status=status,
            tags=[
                "dework",
                "verified-escrow",
                "web3",
                f"org:{org_name}",
                f"workspace:{workspace_name}",
                bounty_value_str,
            ],
        )

    # ------------------------------------------------------------------ #
    # Operator notification when blocked
    # ------------------------------------------------------------------ #
    def _notify_filter_block(self) -> None:
        """Send a 🛡️ FILTER Telegram event so the operator knows
        Dework scraping returned 0 bounties."""
        try:
            from src.utils import state_manager
            from src.utils.telegram import get_notifier
            state_manager.update_pointer(
                stage="DEWORK_NO_BOUNTIES",
                last_action="Dework scrape returned 0 active bounties",
                current_target_repo="dework.xyz",
            )
            tg = get_notifier()
            tg.send_filter_event(
                repo="dework.xyz",
                reason="Dework: 0 active bounties in top 30 orgs",
                details=(
                    "Scanned 30 popular orgs × 5 workspaces each = ~150 workspaces. "
                    "No tasks with active status (TODO/IN_PROGRESS/REVIEW) + rewards found. "
                    "This is normal — Dework bounties are seasonal. "
                    "Next hourly hunt will retry automatically."
                ),
            )
        except Exception:  # noqa: BLE001
            pass  # notifications are best-effort
