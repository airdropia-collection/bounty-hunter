"""
GitHub Issues + PRs client.

Key feature: ``wake_operator()`` — when the bot needs human input,
it creates a GitHub Issue with label ``operator-needed``. The user
gets a push notification on their phone, opens the issue, reads what's
needed, and comments ``/resolve``. The bot continues.

This is the core of the "operator-runner" pattern: the bot is the
primary operator, the user is just the runner who wakes the operator
when help is needed.

Usage:
    from src.utils.github_client import GitHubClient

    gh = GitHubClient()
    gh.wake_operator(
        title="Missing GEMINI_API_KEY secret",
        body="I can't analyze bounties without Gemini. Please add the secret.",
        category="missing_secret",
    )
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from src.utils.logger import get_logger
from src.utils.retry import retry_network
from src.utils.sanitizer import sanitize

log = get_logger("github")


# Labels used across the bot
LABEL_OPERATOR_NEEDED = "operator-needed"
LABEL_BOUNTY_FINDING = "bounty-finding"
LABEL_SUBMITTED = "submitted"
LABEL_ACCEPTED = "accepted"
LABEL_PAID = "paid"
LABEL_REJECTED = "rejected"

ALL_LABELS = [
    LABEL_OPERATOR_NEEDED,
    LABEL_BOUNTY_FINDING,
    LABEL_SUBMITTED,
    LABEL_ACCEPTED,
    LABEL_PAID,
    LABEL_REJECTED,
]


@dataclass
class Issue:
    """A GitHub Issue."""
    number: int
    title: str
    body: str
    labels: list[str]
    url: str
    state: str


class GitHubClient:
    """GitHub REST API wrapper using httpx (sync).

    Reads ``GH_PAT`` and ``GH_REPO`` from env. Falls back to no-op mode
    if credentials are missing (useful for local dev + tests).
    """

    def __init__(self, token: str | None = None, repo: str | None = None):
        self.token = token or os.getenv("GH_PAT", "")
        self.repo = repo or os.getenv("GH_REPO", "")
        self._base = "https://api.github.com"
        self._dry_run = not self.token or not self.repo
        if self._dry_run:
            log.warning(
                "GitHubClient in DRY-RUN mode (no GH_PAT or GH_REPO set). "
                "Issues will be logged but not created."
            )

    # ------------------------------------------------------------------ #
    # Internal HTTP
    # ------------------------------------------------------------------ #
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @retry_network(max_attempts=3, base_delay=1.0, max_delay=5.0)
    def _request(self, method: str, path: str, json_body: dict | None = None) -> dict:
        import httpx

        url = f"{self._base}{path}"
        resp = httpx.request(
            method, url, headers=self._headers(), json=json_body, timeout=30
        )
        if resp.status_code >= 400:
            log.error("GitHub API %s %s failed: %d %s", method, path, resp.status_code, resp.text[:200])
            resp.raise_for_status()
        return resp.json() if resp.text else {}

    # ------------------------------------------------------------------ #
    # Label management
    # ------------------------------------------------------------------ #
    def ensure_labels_exist(self) -> None:
        """Create the standard labels if they don't exist. Safe to call repeatedly."""
        if self._dry_run:
            return
        for label in ALL_LABELS:
            try:
                self._request("POST", f"/repos/{self.repo}/labels", {
                    "name": label,
                    "color": self._label_color(label),
                    "description": self._label_description(label),
                })
            except Exception as exc:  # noqa: BLE001
                # 422 = already exists, that's fine
                if "422" not in str(exc):
                    log.debug("label %s: %s", label, exc)

    @staticmethod
    def _label_color(label: str) -> str:
        return {
            LABEL_OPERATOR_NEEDED: "d73a4a",  # red
            LABEL_BOUNTY_FINDING: "fbca04",   # yellow
            LABEL_SUBMITTED: "0075ca",        # blue
            LABEL_ACCEPTED: "0e8a16",         # green
            LABEL_PAID: "5319e7",             # purple
            LABEL_REJECTED: "b60205",         # dark red
        }.get(label, "ededed")

    @staticmethod
    def _label_description(label: str) -> str:
        return {
            LABEL_OPERATOR_NEEDED: "Bot needs human input to proceed",
            LABEL_BOUNTY_FINDING: "AI-discovered vulnerability finding",
            LABEL_SUBMITTED: "Report submitted to platform",
            LABEL_ACCEPTED: "Submission accepted by platform",
            LABEL_PAID: "Bounty paid out",
            LABEL_REJECTED: "Submission rejected (invalid/duplicate)",
        }.get(label, "")

    # ------------------------------------------------------------------ #
    # Issue operations
    # ------------------------------------------------------------------ #
    def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> Issue | None:
        """Create a GitHub Issue. Returns Issue object or None in dry-run."""
        title = sanitize(title, max_len=200) if not is_safe_title(title) else title
        body = sanitize(body, max_len=50000)

        if self._dry_run:
            log.info("[DRY-RUN] would create Issue: %s (labels=%s)", title, labels)
            return None

        payload = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        result = self._request("POST", f"/repos/{self.repo}/issues", payload)
        issue = Issue(
            number=result.get("number", 0),
            title=result.get("title", title),
            body=result.get("body", body),
            labels=[lbl["name"] for lbl in result.get("labels", [])],
            url=result.get("html_url", ""),
            state=result.get("state", "open"),
        )
        log.info("created Issue #%d: %s (%s)", issue.number, issue.title, issue.url)
        return issue

    def comment_issue(self, issue_number: int, body: str) -> None:
        """Add a comment to an Issue."""
        body = sanitize(body, max_len=50000)
        if self._dry_run:
            log.info("[DRY-RUN] would comment on #%d: %s", issue_number, body[:100])
            return
        self._request("POST", f"/repos/{self.repo}/issues/{issue_number}/comments", {"body": body})
        log.info("commented on #%d", issue_number)

    def close_issue(self, issue_number: int, reason: str = "completed") -> None:
        """Close an Issue."""
        if self._dry_run:
            log.info("[DRY-RUN] would close #%d (%s)", issue_number, reason)
            return
        self._request("PATCH", f"/repos/{self.repo}/issues/{issue_number}", {
            "state": "closed",
            "state_reason": reason,
        })
        log.info("closed #%d (%s)", issue_number, reason)

    def add_labels(self, issue_number: int, labels: list[str]) -> None:
        """Add labels to an Issue."""
        if self._dry_run:
            return
        self._request("POST", f"/repos/{self.repo}/issues/{issue_number}/labels", {"labels": labels})

    def get_issue(self, issue_number: int) -> Issue | None:
        """Fetch an Issue by number."""
        if self._dry_run:
            return None
        try:
            result = self._request("GET", f"/repos/{self.repo}/issues/{issue_number}")
            return Issue(
                number=result.get("number", 0),
                title=result.get("title", ""),
                body=result.get("body", ""),
                labels=[lbl["name"] for lbl in result.get("labels", [])],
                url=result.get("html_url", ""),
                state=result.get("state", "open"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("could not fetch issue #%d: %s", issue_number, exc)
            return None

    def list_open_issues(self, label: str | None = None) -> list[Issue]:
        """List open issues, optionally filtered by label."""
        if self._dry_run:
            return []
        params = {"state": "open", "per_page": 100}
        if label:
            params["labels"] = label
        import httpx
        resp = httpx.get(
            f"{self._base}/repos/{self.repo}/issues",
            headers=self._headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return [
            Issue(
                number=i.get("number", 0),
                title=i.get("title", ""),
                body=i.get("body", "") or "",
                labels=[lbl["name"] for lbl in i.get("labels", [])],
                url=i.get("html_url", ""),
                state=i.get("state", "open"),
            )
            for i in resp.json()
            if "pull_request" not in i  # filter out PRs
        ]

    # ------------------------------------------------------------------ #
    # Wake-the-operator
    # ------------------------------------------------------------------ #
    def wake_operator(
        self,
        title: str,
        body: str,
        category: str = "general",
        context: dict[str, Any] | None = None,
    ) -> Issue | None:
        """Wake the human operator.

        Creates a GitHub Issue with label ``operator-needed``. The user
        gets a notification on their phone. They resolve it by either:
        - Fixing the issue (e.g., adding a secret) and commenting ``/resolve``
        - Commenting ``/resolve <instruction>`` to give the bot guidance

        Args:
            title: short headline (max 200 chars)
            body: detailed description of what's needed
            category: for grouping (missing_secret, ambiguous_finding,
                     submission_approval, bug, etc.)
            context: optional dict with extra data (rendered as code block)

        Returns: Issue object or None if dry-run.
        """
        full_body = f"""## 🤖 Operator Assistance Needed

**Category:** `{category}`

{body}
"""
        if context:
            full_body += f"""
### Context
```json
{json.dumps(sanitize(context), indent=2, default=str)}
```
"""
        full_body += """
### How to resolve
- Fix the issue (e.g., add the missing secret)
- Then comment: `/resolve fixed`
- Or comment: `/resolve <instruction>` to give the bot guidance

---
*This Issue was auto-created by the bounty-hunter bot. The bot is paused until you resolve it.*
"""
        return self.create_issue(
            title=f"🤖 [OPERATOR] {title}",
            body=full_body,
            labels=[LABEL_OPERATOR_NEEDED],
        )

    def is_operator_needed(self) -> bool:
        """Check if there are any open operator-needed issues."""
        issues = self.list_open_issues(label=LABEL_OPERATOR_NEEDED)
        return len(issues) > 0


def is_safe_title(title: str) -> bool:
    """Check if a title contains no secrets (titles can't be sanitized aggressively)."""
    from src.utils.sanitizer import is_safe_to_log
    return is_safe_to_log(title)
