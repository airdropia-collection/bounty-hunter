"""
Platform Onboarding & Pre-PR Requirements Checker.

Each verified escrow platform has its own contribution policy that must be
satisfied BEFORE the bot submits a PR. Skipping these "gates" results in
the maintainer blocking the PR (as happened with MergeOS Gate 1 on
PR #252 — see docs/platform_policies/mergeos.md).

This module:
1. Defines per-platform onboarding requirements (follow / star / sign CLA /
   accept terms / etc.)
2. Verifies each requirement via the GitHub API before a PR is submitted
3. If any requirement is missing, BLOCKS the PR submission and emits a
   🛡️ FILTER Telegram event with the exact missing actions
4. Provides an evidence template the operator can paste into the PR comment
   once they've manually completed the actions (where the bot's PAT scope
   is insufficient — e.g. follow/star require user-level PAT scopes)

Currently supported platforms:
- mergeos-bounties: 4-gate policy (badges → security → tests → merge)
- issuehunt:        no onboarding required (just fund the bounty)
- bountycaster:     no onboarding required (Farcaster-native)

To add a new platform, register it in PLATFORM_REQUIREMENTS below.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from src.utils.logger import get_logger

log = get_logger("platform_onboarding")


# --------------------------------------------------------------------------- #
# GitHub API helpers
# --------------------------------------------------------------------------- #
def _get_pat() -> str:
    """Extract the GitHub PAT from the local git remote URL.
    Falls back to GH_PAT / GITHUB_TOKEN env vars.
    """
    for env_var in ("GH_PAT", "GITHUB_TOKEN"):
        token = os.getenv(env_var, "").strip()
        if token:
            return token
    try:
        return subprocess.check_output(
            ["bash", "-c",
             "git config --get remote.origin.url | "
             "sed -n 's|https://x-access-token:\\([^@]*\\)@.*|\\1|p'"],
            cwd="/home/z/my-project/bounty-hunter",
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:  # noqa: BLE001
        return ""


def _gh_request(method: str, url: str, data: dict | None = None) -> tuple[int, str]:
    """Return (status_code, body_text). Status 0 = network error."""
    pat = _get_pat()
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "bounty-hunter-bot/1.0",
        "Content-Type": "application/json",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


# --------------------------------------------------------------------------- #
# Requirement dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class Requirement:
    """A single onboarding requirement for a platform."""
    kind: str  # "follow" | "star" | "cla" | "terms" | "manual"
    target: str  # e.g. "mergeos-bounties" (org) or "mergeos-bounties/mergeos" (repo)
    label: str  # human-readable label
    evidence_url: str = ""  # URL that proves completion (for the PR comment)


@dataclass
class PlatformPolicy:
    """Full onboarding policy for a platform."""
    platform: str
    requirements: list[Requirement] = field(default_factory=list)
    gate_order: list[str] = field(default_factory=list)  # e.g. ["badges", "security", "tests", "merge"]
    policy_doc_url: str = ""
    notes: str = ""


# --------------------------------------------------------------------------- #
# Registered platform policies
# --------------------------------------------------------------------------- #
PLATFORM_REQUIREMENTS: dict[str, PlatformPolicy] = {
    "mergeos": PlatformPolicy(
        platform="mergeos",
        requirements=[
            Requirement(
                kind="follow",
                target="mergeos-bounties",
                label="Follow the mergeos-bounties org",
                evidence_url="https://github.com/mergeos-bounties",
            ),
            Requirement(
                kind="star",
                target="mergeos-bounties/mergeos",
                label="Star mergeos-bounties/mergeos (core repo)",
                evidence_url="https://github.com/mergeos-bounties/mergeos",
            ),
            Requirement(
                kind="star",
                target="mergeos-bounties/mergeos-contracts",
                label="Star mergeos-bounties/mergeos-contracts (core repo)",
                evidence_url="https://github.com/mergeos-bounties/mergeos-contracts",
            ),
        ],
        gate_order=["badges", "security", "tests", "merge"],
        policy_doc_url="https://github.com/mergeos-bounties",
        notes=(
            "MergeOS enforces a 4-gate policy: badges → security → tests → merge. "
            "Gate 1 (badges) requires following the org AND starring BOTH core "
            "repos. Starring only the product repo (e.g. Loru) is NOT enough. "
            "If Gate 1 is not satisfied, the maintainer blocks the PR with a "
            "comment like 'Gate 1 (badges) blocked'."
        ),
    ),
    # IssueHunt: no onboarding requirements (just fund the bounty)
    "issuehunt": PlatformPolicy(
        platform="issuehunt",
        requirements=[],
        gate_order=["bounty_funded", "pr_submitted", "reviewer_approves", "payout"],
        notes="IssueHunt has no pre-PR onboarding requirements. Bounties are escrow-funded.",
    ),
    # Bountycaster: no onboarding requirements (Farcaster-native)
    "bountycaster": PlatformPolicy(
        platform="bountycaster",
        requirements=[],
        gate_order=["cast_bounty", "pr_submitted", "reviewer_approves", "payout"],
        notes="Bountycaster is Farcaster-native; no GitHub-side onboarding required.",
    ),
}


# --------------------------------------------------------------------------- #
# Detect platform from upstream repo
# --------------------------------------------------------------------------- #
def detect_platform(upstream_repo: str) -> str | None:
    """Detect which verified platform an upstream repo belongs to.

    Args:
        upstream_repo: e.g. "mergeos-bounties/Loru" or "marcosgriselli/SwipeableTabBarController"

    Returns:
        Platform key ("mergeos", "issuehunt", "bountycaster") or None.
    """
    repo_lower = upstream_repo.lower()

    # MergeOS bounties are all under the mergeos-bounties org
    if repo_lower.startswith("mergeos-bounties/"):
        return "mergeos"

    # IssueHunt bounties can be under any repo — but only count as IssueHunt
    # if the issue body contains the IssueHunt badge. The caller is responsible
    # for passing only IssueHunt-funded repos here.
    # For now, we return None for non-mergeos repos unless explicitly tagged.
    return None


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
def verify_requirement(req: Requirement) -> tuple[bool, str]:
    """Verify a single requirement via the GitHub API.

    Returns (is_satisfied, detail_message).
    """
    if req.kind == "follow":
        status, _ = _gh_request("GET", f"https://api.github.com/user/following/{req.target}")
        if status == 204:
            return True, f"✅ Following {req.target}"
        elif status == 403:
            return False, (
                f"⚠️ PAT scope insufficient to verify follow on {req.target} "
                f"(HTTP 403 — needs 'user:follow' scope on Classic PAT or "
                f"'Followers' permission on fine-grained PAT). "
                f"Manual check required."
            )
        elif status == 404:
            return False, f"❌ Not following {req.target}"
        else:
            return False, f"❓ HTTP {status} checking follow on {req.target}"

    if req.kind == "star":
        status, _ = _gh_request("GET", f"https://api.github.com/user/starred/{req.target}")
        if status == 204:
            return True, f"✅ Starred {req.target}"
        elif status == 403:
            return False, (
                f"⚠️ PAT scope insufficient to verify star on {req.target} "
                f"(HTTP 403 — needs 'public_repo' scope on Classic PAT or "
                f"'Starring' permission on fine-grained PAT). "
                f"Manual check required."
            )
        elif status == 404:
            return False, f"❌ Not starred {req.target}"
        else:
            return False, f"❓ HTTP {status} checking star on {req.target}"

    if req.kind in ("cla", "terms", "manual"):
        # These can't be verified via API — always return "manual check needed"
        return False, f"⚠️ Manual action required: {req.label}"

    return False, f"❓ Unknown requirement kind: {req.kind}"


def verify_all_requirements(platform: str) -> dict[str, Any]:
    """Verify all onboarding requirements for a platform.

    Returns a dict with:
    - "platform": platform name
    - "all_satisfied": bool
    - "satisfied_count": int
    - "total_count": int
    - "requirements": list of {requirement, satisfied, detail}
    - "missing_actions": list of human-readable missing actions
    - "evidence_template": markdown text for pasting into PR comment
    """
    policy = PLATFORM_REQUIREMENTS.get(platform)
    if not policy:
        return {
            "platform": platform,
            "all_satisfied": True,  # no policy = no requirements
            "satisfied_count": 0,
            "total_count": 0,
            "requirements": [],
            "missing_actions": [],
            "evidence_template": "",
        }

    results = []
    satisfied_count = 0
    missing_actions = []

    for req in policy.requirements:
        satisfied, detail = verify_requirement(req)
        results.append({
            "requirement": req,
            "satisfied": satisfied,
            "detail": detail,
        })
        if satisfied:
            satisfied_count += 1
        else:
            missing_actions.append(f"- [ ] {req.label}: {req.evidence_url}")

    all_satisfied = satisfied_count == len(policy.requirements)

    # Build evidence template (for PR comment once user completes actions)
    evidence_template = ""
    if not all_satisfied:
        evidence_template = (
            f"## {platform.title()} Gate 1 — Onboarding Checklist\n\n"
            f"Per the {platform} bounty policy ({policy.policy_doc_url}), "
            f"completing the following before PR review:\n\n"
            + "\n".join(missing_actions)
            + "\n\n---\n"
            + "_Evidence of completion will be attached once verified._\n"
        )

    return {
        "platform": platform,
        "all_satisfied": all_satisfied,
        "satisfied_count": satisfied_count,
        "total_count": len(policy.requirements),
        "requirements": results,
        "missing_actions": missing_actions,
        "evidence_template": evidence_template,
        "policy": policy,
    }


# --------------------------------------------------------------------------- #
# Top-level entrypoint
# --------------------------------------------------------------------------- #
def check_onboarding(upstream_repo: str) -> dict[str, Any]:
    """Check whether the bot is onboarded for the platform that owns
    `upstream_repo`. Returns the verification result dict.

    If the platform has no requirements (e.g. IssueHunt, Bountycaster),
    returns all_satisfied=True immediately.
    """
    platform = detect_platform(upstream_repo)
    if platform is None:
        # Unknown platform — assume no onboarding needed (IssueHunt-style)
        log.info("[%s] no platform policy registered — skipping onboarding check", upstream_repo)
        return {
            "platform": "unknown",
            "all_satisfied": True,
            "satisfied_count": 0,
            "total_count": 0,
            "requirements": [],
            "missing_actions": [],
            "evidence_template": "",
        }

    log.info("[%s] checking %s onboarding requirements...", upstream_repo, platform)
    result = verify_all_requirements(platform)

    if result["all_satisfied"]:
        log.info("[%s] ✅ all %d %s requirements satisfied",
                 upstream_repo, result["total_count"], platform)
    else:
        log.warning("[%s] ❌ %d/%d %s requirements missing: %s",
                    upstream_repo,
                    result["total_count"] - result["satisfied_count"],
                    result["total_count"],
                    platform,
                    ", ".join(result["missing_actions"]))

    return result


def block_pr_if_not_onboarded(upstream_repo: str) -> bool:
    """Return True if PR submission should be BLOCKED because onboarding
    is incomplete. Also sends a 🛡️ FILTER Telegram event if blocked.

    Usage in submit-pr.yml:
        python -c "from src.utils.platform_onboarding import block_pr_if_not_onboarded as b; import sys; sys.exit(1 if b('mergeos-bounties/Loru') else 0)"
    """
    result = check_onboarding(upstream_repo)

    if result["all_satisfied"]:
        return False  # don't block

    # Send Telegram 🛡️ FILTER event
    try:
        from src.utils import state_manager
        from src.utils.telegram import get_notifier
        state_manager.update_pointer(
            stage="ONBOARDING_BLOCKED",
            last_action=f"PR submission blocked — {result['platform']} onboarding incomplete",
            current_target_repo=upstream_repo,
        )
        tg = get_notifier()
        missing_lines = "\n".join(result["missing_actions"]) or "(no specific actions listed)"
        tg.send_filter_event(
            repo=upstream_repo,
            reason=f"{result['platform'].title()} Gate 1 onboarding incomplete",
            details=(
                f"Missing {result['total_count'] - result['satisfied_count']}/{result['total_count']} "
                f"requirements for {result['platform']}:\n{missing_lines}\n\n"
                f"PR submission BLOCKED until onboarding complete."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("could not send Telegram filter event: %s", exc)

    return True  # block


# --------------------------------------------------------------------------- #
# CLI entrypoint
# --------------------------------------------------------------------------- #
def _cli() -> int:
    import sys
    if len(sys.argv) < 2:
        print("usage: python -m src.utils.platform_onboarding <upstream_repo>")
        print("       python -m src.utils.platform_onboarding mergeos-bounties/Loru")
        return 1

    upstream = sys.argv[1]
    result = check_onboarding(upstream)
    print(f"\n=== Onboarding check for {upstream} ===")
    print(f"Platform: {result['platform']}")
    print(f"All satisfied: {result['all_satisfied']}")
    print(f"Satisfied: {result['satisfied_count']}/{result['total_count']}")
    if result.get("policy"):
        print(f"Gate order: {' → '.join(result['policy'].gate_order)}")
        print(f"Notes: {result['policy'].notes}")
    print()
    if result["requirements"]:
        print("=== Requirements ===")
        for r in result["requirements"]:
            mark = "✅" if r["satisfied"] else "❌"
            print(f"  {mark} {r['requirement'].label}: {r['detail']}")
        print()
    if result["missing_actions"]:
        print("=== Missing actions ===")
        for action in result["missing_actions"]:
            print(f"  {action}")
        print()
        print("=== Evidence template (paste into PR comment once complete) ===")
        print(result["evidence_template"])

    return 0 if result["all_satisfied"] else 2


if __name__ == "__main__":
    raise SystemExit(_cli())
