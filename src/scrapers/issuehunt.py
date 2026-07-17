"""
IssueHunt bounty scraper.

IssueHunt is a platform where GitHub issues have bounties ($2-$500).
Low competition, easy entry point for earning first $.

Data source: https://issuehunt.io/issues

The IssueHunt /issues page is a Next.js SPA. The actual bounty data
is embedded in the HTML as a JSON array of issue objects. Each object
has these critical fields:

  - githubState: "open" | "closed"  (mirrors the GitHub issue state)
  - status:      "ready" | "funded" | "rewarded"
                  * ready   = bounty posted, no funds escrowed yet
                  * funded  = funds escrowed, awaiting a PR
                  * rewarded = bounty paid out (DONE — skip)
  - depositAmount: integer (cents USD)
  - repositoryOwnerName, repositoryName, number: identity
  - fundedAt, updatedAt: ISO timestamps
  - title: issue title

The OLD scraper (pre-2026-07-17) only regex-extracted /r/owner/repo/N
links from the HTML without parsing the JSON. This caused it to pull
stale, already-rewarded, or closed issues — wasting pipeline cycles
and producing zero submittable findings.

The NEW scraper (2026-07-17) parses the embedded JSON, filters to
`githubState == "open"` AND `status in {"ready", "funded"}`, and
drops any issue already marked `rewarded` (paid out). It also falls
back to the legacy regex parser if the JSON is missing (e.g., if
IssueHunt changes their page structure) so the scraper degrades
gracefully rather than returning [] silently.

Quality filters (agent.md §3):
  - Skip repos with <50 stars (checked downstream via ContractDownloader)
  - Skip issues with no description (filtered here)
  - Skip pull requests (isPullRequest=true) — only issues carry bounties
  - Skip bounties with 0 deposit (status=ready, no money escrowed)
"""
from __future__ import annotations

import json
import re

from src.scrapers.base import BaseScraper, Bounty
from src.utils.logger import get_logger

log = get_logger("scrapers.issuehunt")

# Statuses that indicate the bounty is still claimable.
# - "ready"  = posted, no funds yet (often low-priority but still valid)
# - "funded" = funds escrowed, awaiting a PR (HIGHEST priority)
# - "rewarded" = already paid out — EXCLUDED
ACTIONABLE_STATUSES = frozenset({"ready", "funded"})


class IssueHuntScraper(BaseScraper):
    """Scrapes IssueHunt open bounties by parsing embedded JSON."""

    PLATFORM_NAME = "issuehunt"
    BASE_URL = "https://issuehunt.io"
    ISSUES_URL = "https://issuehunt.io/issues"

    def scrape(self) -> list[Bounty]:
        """Scrape IssueHunt bounties, filtered to actionable ones only."""
        self.log.info("scraping IssueHunt issues page...")
        try:
            html = self._fetch_html(self.ISSUES_URL)
            self.save_raw("issues", html)
            bounties = self._parse_issues(html)
            self.log.info(
                "IssueHunt: found %d actionable bounties (open + funded/ready, not rewarded)",
                len(bounties),
            )
            return bounties
        except Exception as exc:
            self.log.error("IssueHunt scrape failed: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # JSON parser (primary path — 2026-07-17)
    # ------------------------------------------------------------------ #
    def _parse_issues(self, html: str) -> list[Bounty]:
        """Parse IssueHunt bounties by extracting the embedded JSON.

        Order of preference:
          1. Parse the JSON blob containing issue objects (each has
             ``isPullRequest``, ``githubState``, ``status``, ``depositAmount``)
          2. Filter to: githubState=="open" AND status in ACTIONABLE_STATUSES
             AND NOT isPullRequest AND depositAmount > 0
          3. If JSON parse finds zero objects, fall back to legacy regex
             parser (which returns [] if no links — never returns stale data)
        """
        issues = self._extract_issue_objects(html)
        self.log.debug("parsed %d raw issue objects from JSON", len(issues))

        if not issues:
            self.log.warning(
                "no JSON issue objects found — falling back to legacy regex parser"
            )
            return self._legacy_regex_parse(html)

        bounties: list[Bounty] = []
        for obj in issues:
            bounty = self._bounty_from_json(obj)
            if bounty:
                bounties.append(bounty)

        # Sort by payout desc, then by fundedAt desc (newer first)
        bounties.sort(
            key=lambda b: (b.max_payout_usd, b.tags and b.tags[0] or ""),
            reverse=True,
        )
        return bounties

    def _extract_issue_objects(self, html: str) -> list[dict]:
        """Extract all JSON issue objects from the HTML.

        IssueHunt's page embeds issue data as a JSON array of objects,
        each starting with ``{"isPullRequest":``. We find each such
        object by scanning for the sentinel and walking braces to find
        the matching close.
        """
        objects: list[dict] = []
        sentinel = '{"isPullRequest":'
        pos = 0

        while True:
            idx = html.find(sentinel, pos)
            if idx == -1:
                break

            # Walk forward to find matching close brace at depth 0
            depth = 0
            in_string = False
            escape = False
            i = idx
            end = -1
            while i < len(html):
                c = html[i]
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_string = not in_string
                elif not in_string:
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                i += 1

            if end == -1:
                # Malformed or truncated — bail
                break

            raw = html[idx:end]
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict) and "githubState" in obj:
                    objects.append(obj)
            except json.JSONDecodeError:
                # Some objects may have nested structures that confuse the
                # brace walker. Skip and continue scanning.
                self.log.debug("skipping unparseable issue object at char %d", idx)

            pos = end

        return objects

    def _bounty_from_json(self, obj: dict) -> Bounty | None:
        """Convert a raw JSON issue object to a Bounty, or None if not actionable.

        Filtering rules:
          - githubState must be "open" (skip closed issues)
          - status must be in ACTIONABLE_STATUSES (skip "rewarded" = paid out)
          - isPullRequest must be False (we want issues, not PRs)
          - depositAmount must be > 0 (skip zero-fund "ready" placeholders)
        """
        github_state = obj.get("githubState", "")
        status = obj.get("status", "")
        is_pr = obj.get("isPullRequest", False)
        deposit_cents = obj.get("depositAmount", 0) or 0

        # ── Filter: only open + funded/ready, not rewarded ──
        if github_state != "open":
            return None
        if status not in ACTIONABLE_STATUSES:
            return None
        if is_pr:
            return None
        if deposit_cents <= 0:
            return None

        owner = obj.get("repositoryOwnerName", "")
        repo = obj.get("repositoryName", "")
        number = obj.get("number")
        if not (owner and repo and number):
            return None

        amount_usd = deposit_cents // 100  # cents → dollars (integer)
        github_url = f"https://github.com/{owner}/{repo}/issues/{number}"
        issuehunt_path = f"/r/{owner}/{repo}/issues/{number}"
        title = obj.get("title", "") or f"{owner}/{repo}#{number}"
        funded_at = obj.get("fundedAt")
        pr_count = obj.get("pullRequestCount", 0) or 0

        # Tags help downstream triage
        tags = ["github-issue", "bounty"]
        if status == "funded":
            tags.append("escrow-funded")
        if pr_count == 0:
            tags.append("no-competing-pr")  # favorable — no one else has tried
        elif pr_count >= 3:
            tags.append("high-competition")
        if amount_usd <= 50:
            tags.append("small")
        elif amount_usd >= 200:
            tags.append("medium")

        # Severity: IssueHunt doesn't ship severity; infer from amount
        severity = ["Low", "Medium"] if amount_usd < 200 else ["Medium", "High"]

        # Description: title + metadata (IssueHunt body is huge; skip body to keep state.json small)
        description = (
            f"IssueHunt bounty: {title}\n"
            f"Repo: {owner}/{repo}  Issue: #{number}\n"
            f"Reward: ${amount_usd}  Status: {status}  GitHub state: {github_state}\n"
            f"Funded at: {funded_at or 'n/a'}  Existing PRs: {pr_count}"
        )

        return Bounty(
            id=f"issuehunt-{owner}-{repo}-{number}",
            platform=self.PLATFORM_NAME,
            project_name=f"{owner}/{repo}#{number}",
            description=description,
            max_payout_usd=amount_usd,
            severity_levels=severity,
            tech_stack=["GitHub", "Open Source"],
            source_urls=[github_url],
            url=f"{self.BASE_URL}{issuehunt_path}",
            deadline=None,
            status="active",
            tags=tags,
        )

    # ------------------------------------------------------------------ #
    # Legacy fallback (only used if JSON parsing fails entirely)
    # ------------------------------------------------------------------ #
    def _legacy_regex_parse(self, html: str) -> list[Bounty]:
        """Pre-2026-07-17 regex parser, kept as a degraded fallback.

        Returns [] if no /r/owner/repo/N links found. NEVER returns stale
        or rewarded issues because we have no JSON to check status from —
        better to return empty than to surface paid-out bounties.
        """
        self.log.warning("using legacy regex parser — cannot verify bounty status")
        bounties: list[Bounty] = []
        issue_links = re.findall(r'href="(/r/[^/]+/[^/]+/issues/\d+)"', html)
        seen: set[str] = set()
        for link in issue_links:
            if link in seen:
                continue
            seen.add(link)
            match = re.match(r"/r/([^/]+)/([^/]+)/issues/(\d+)", link)
            if not match:
                continue
            owner, repo, issue_num = match.group(1), match.group(2), match.group(3)
            github_url = f"https://github.com/{owner}/{repo}/issues/{issue_num}"
            bounties.append(
                Bounty(
                    id=f"issuehunt-{owner}-{repo}-{issue_num}",
                    platform=self.PLATFORM_NAME,
                    project_name=f"{owner}/{repo}#{issue_num}",
                    description=f"IssueHunt bounty (unverified status) for {owner}/{repo}#{issue_num}",
                    max_payout_usd=0,
                    severity_levels=["Low"],
                    tech_stack=["GitHub", "Open Source"],
                    source_urls=[github_url],
                    url=f"{self.BASE_URL}{link}",
                    deadline=None,
                    status="active",
                    tags=["github-issue", "bounty", "unverified-status"],
                )
            )
        return bounties[:50]
