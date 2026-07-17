"""
Central State Manager (Save-Game Engine).

This module is the SINGLE source of truth for the bot's persistent state.
It reads/writes the root-level ``state.json`` file that every AI agent,
GitHub Action, and Telegram callback handler MUST consult before acting.

The state file schema is defined in ``agent.md`` and includes:
- ``system_status``: "RUNNING" or "PAUSED" (the master brake)
- ``current_execution_pointer``: where the bot is right now
- ``active_monitors``: PRs under review (NEVER delete these forks)
- ``blacklisted_repos``: repos we will never touch again

CRITICAL RULE (from agent.md §2):
    If ``system_status == "PAUSED"``, every loop / workflow MUST exit
    immediately without performing any hunting, scraping, or PR submission.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger("state_manager")

# The state file lives at the REPO ROOT, not under state/.
# Resolve relative to this file so it works from any CWD (GitHub Actions
# checks out the repo to $GITHUB_WORKSPACE, and `src/utils/state_manager.py`
# is always at <root>/src/utils/state_manager.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = _REPO_ROOT / "state.json"

# Statuses that protect a fork from deletion (agent.md §5)
PROTECTED_PR_STATUSES = {"UNDER_REVIEW", "NEEDS_REVISION"}
# Statuses that allow fork deletion (agent.md §5)
DELETABLE_PR_STATUSES = {"MERGED", "CLOSED_AND_REJECTED"}


# --------------------------------------------------------------------------- #
# Default state (used if file is missing or corrupt)
# --------------------------------------------------------------------------- #
DEFAULT_STATE: dict[str, Any] = {
    "system_status": "RUNNING",
    "last_session_sync": datetime.now(UTC).isoformat(),
    "current_execution_pointer": {
        "stage": "INIT",
        "last_action": "state.json initialized",
        "current_target_repo": "NONE",
    },
    "active_monitors": {},
    "blacklisted_repos": [],
}


# --------------------------------------------------------------------------- #
# Core read / write
# --------------------------------------------------------------------------- #
def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Atomic write — write to a temp file then rename, so partial
    writes never corrupt the state file if the process is killed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def read_state() -> dict[str, Any]:
    """Read the state file. Returns a deep copy of DEFAULT_STATE if
    the file is missing or unparseable (never raises)."""
    if not STATE_FILE.exists():
        log.warning("state.json missing — initializing with defaults")
        _atomic_write(STATE_FILE, DEFAULT_STATE)
        return json.loads(json.dumps(DEFAULT_STATE))  # deep copy

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        # Ensure all top-level keys exist
        for k, v in DEFAULT_STATE.items():
            data.setdefault(k, json.loads(json.dumps(v)))
        return data
    except Exception as exc:  # noqa: BLE001
        log.error("state.json corrupt (%s) — reinitializing", exc)
        _atomic_write(STATE_FILE, DEFAULT_STATE)
        return json.loads(json.dumps(DEFAULT_STATE))


def write_state(state: dict[str, Any]) -> None:
    """Persist the full state dict to disk atomically."""
    state["last_session_sync"] = datetime.now(UTC).isoformat()
    try:
        _atomic_write(STATE_FILE, state)
        log.debug("state.json updated: status=%s monitors=%d",
                  state.get("system_status"),
                  len(state.get("active_monitors", {})))
    except Exception as exc:  # noqa: BLE001
        log.error("could not write state.json: %s", exc)


# --------------------------------------------------------------------------- #
# Master brake (PAUSED / RUNNING)
# --------------------------------------------------------------------------- #
def is_paused() -> bool:
    """Return True if system_status is PAUSED. Every workflow MUST
    check this before doing any work."""
    return read_state().get("system_status", "RUNNING").upper() == "PAUSED"


def is_running() -> bool:
    return not is_paused()


def pause() -> bool:
    """Set system_status to PAUSED. Returns True if state changed."""
    state = read_state()
    if state.get("system_status") == "PAUSED":
        return False
    state["system_status"] = "PAUSED"
    write_state(state)
    log.warning("🛑 SYSTEM PAUSED by operator")
    return True


def resume() -> bool:
    """Set system_status to RUNNING. Returns True if state changed."""
    state = read_state()
    if state.get("system_status") == "RUNNING":
        return False
    state["system_status"] = "RUNNING"
    write_state(state)
    log.info("▶️ SYSTEM RESUMED by operator")
    return True


# --------------------------------------------------------------------------- #
# Execution pointer (where the bot is right now)
# --------------------------------------------------------------------------- #
def update_pointer(
    stage: str,
    last_action: str,
    current_target_repo: str = "NONE",
) -> None:
    """Update the execution pointer. Call this after every major action."""
    state = read_state()
    state["current_execution_pointer"] = {
        "stage": stage,
        "last_action": last_action,
        "current_target_repo": current_target_repo,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    write_state(state)


# --------------------------------------------------------------------------- #
# Active PR monitors (protects forks from deletion)
# --------------------------------------------------------------------------- #
def add_monitor(
    repo: str,
    pr_number: int | str,
    status: str = "UNDER_REVIEW",
    bounty_value: str = "",
    platform: str = "",
) -> None:
    """Register a PR under active monitoring. Fork cleanup MUST NOT
    delete a fork whose upstream repo has an active monitor with a
    protected status (UNDER_REVIEW or NEEDS_REVISION)."""
    state = read_state()
    state["active_monitors"][repo] = {
        "pr_number": int(pr_number) if str(pr_number).isdigit() else pr_number,
        "status": status,
        "bounty_value": bounty_value,
        "platform": platform,
        "added_at": datetime.now(UTC).isoformat(),
    }
    write_state(state)


def update_monitor_status(repo: str, status: str) -> bool:
    """Update the status of an existing monitor. Returns False if not found.
    Allowed statuses: UNDER_REVIEW, NEEDS_REVISION, MERGED, CLOSED_AND_REJECTED."""
    state = read_state()
    monitors = state.get("active_monitors", {})
    if repo not in monitors:
        return False
    monitors[repo]["status"] = status
    monitors[repo]["updated_at"] = datetime.now(UTC).isoformat()
    write_state(state)
    log.info("monitor[%s] status -> %s", repo, status)
    return True


def remove_monitor(repo: str) -> bool:
    """Remove a monitor entirely (used after fork is deleted)."""
    state = read_state()
    monitors = state.get("active_monitors", {})
    if repo not in monitors:
        return False
    del monitors[repo]
    write_state(state)
    return True


def get_monitor(repo: str) -> dict[str, Any] | None:
    return read_state().get("active_monitors", {}).get(repo)


def is_fork_protected(upstream_repo: str) -> bool:
    """Return True if the upstream repo has an active monitor with a
    protected status (UNDER_REVIEW / NEEDS_REVISION). Fork cleanup
    MUST skip these forks."""
    monitor = get_monitor(upstream_repo)
    if not monitor:
        return False
    return monitor.get("status", "").upper() in PROTECTED_PR_STATUSES


def all_protected_repos() -> list[str]:
    """Return list of all upstream repo names with protected PR status."""
    monitors = read_state().get("active_monitors", {})
    return [
        repo for repo, m in monitors.items()
        if m.get("status", "").upper() in PROTECTED_PR_STATUSES
    ]


# --------------------------------------------------------------------------- #
# Blacklist (never touch these repos)
# --------------------------------------------------------------------------- #
def add_blacklist(repo: str, reason: str = "") -> None:
    """Add a repo to the blacklist. Subsequent scrape/analyze cycles
    MUST skip these repos entirely."""
    state = read_state()
    bl = state.setdefault("blacklisted_repos", [])
    # Support both bare strings and {repo, reason} dicts
    existing = {item if isinstance(item, str) else item.get("repo") for item in bl}
    if repo in existing:
        return
    if reason:
        bl.append({"repo": repo, "reason": reason, "added_at": datetime.now(UTC).isoformat()})
    else:
        bl.append(repo)
    write_state(state)
    log.info("🛡️ BLACKLISTED: %s (%s)", repo, reason or "no reason")


def is_blacklisted(repo: str) -> bool:
    """Check if a repo name is in the blacklist.

    Matches flexibly: bounty.project_name often includes a '#N' suffix
    (e.g., 'zardoy/space-squid#5') but the blacklist stores just the
    repo path ('zardoy/space-squid'). We match if:
      - exact equality, OR
      - the input starts with '<blacklisted_entry>#' (issue suffix), OR
      - the input starts with '<blacklisted_entry>/' (subpath)
    """
    if not repo:
        return False
    state = read_state()
    bl = state.get("blacklisted_repos", [])
    for item in bl:
        if isinstance(item, str):
            entry = item
        elif isinstance(item, dict):
            entry = item.get("repo", "")
        else:
            continue
        if not entry:
            continue
        # Exact match
        if entry == repo:
            return True
        # Issue-suffix match: 'zardoy/space-squid' matches 'zardoy/space-squid#5'
        if repo.startswith(entry + "#"):
            return True
        # Subpath match: 'zardoy/space-squid' matches 'zardoy/space-squid/sub'
        if repo.startswith(entry + "/"):
            return True
    return False


def all_blacklisted() -> list[str]:
    """Return list of blacklisted repo names (strings only)."""
    bl = read_state().get("blacklisted_repos", [])
    return [item if isinstance(item, str) else item.get("repo", "") for item in bl]


# --------------------------------------------------------------------------- #
# Snapshot (for Telegram / debugging)
# --------------------------------------------------------------------------- #
def snapshot() -> str:
    """Return a compact human-readable snapshot of the state.
    Designed for non-tech users — shows portfolio summary + per-PR status.
    """
    s = read_state()
    status_emoji = "▶️" if s.get("system_status") == "RUNNING" else "🛑"
    monitors = s.get("active_monitors", {})
    bl = s.get("blacklisted_repos", [])
    ptr = s.get("current_execution_pointer", {})

    # Compute total bounty value at stake
    total_usd = 0
    total_other = []
    for repo, m in monitors.items():
        bv = str(m.get("bounty_value", ""))
        if bv.startswith("$"):
            try:
                total_usd += int(float(bv.replace("$", "").replace(",", "")))
            except ValueError:
                pass
        elif bv and bv != "NONE":
            total_other.append(bv)

    total_str = f"${total_usd}"
    if total_other:
        total_str += " + " + " + ".join(total_other)

    lines = [
        f"{status_emoji} *System:* `{s.get('system_status', 'UNKNOWN')}`",
        f"💰 *Total at stake:* `{total_str}`",
        f"👁️ *Active PRs:* {len(monitors)}",
        f"🚫 *Blacklisted:* {len(bl)} repos",
        f"📍 *Stage:* `{ptr.get('stage', '?')}`",
        f"📝 *Last:* {ptr.get('last_action', '?')[:80]}",
    ]

    # Show each active PR with its status
    if monitors:
        lines.append("")
        lines.append("*📋 PR Portfolio:*")
        for repo, m in monitors.items():
            status_emoji_pr = {
                "UNDER_REVIEW": "👀",
                "NEEDS_REVISION": "🔧",
                "MERGED": "🎉",
                "CLOSED_AND_REJECTED": "❌",
            }.get(m.get("status", ""), "❓")
            bv = m.get("bounty_value", "?")
            pr_num = m.get("pr_number", "?")
            # Shorten repo name for readability
            short_repo = repo.split("/")[-1] if "/" in repo else repo
            lines.append(
                f"  {status_emoji_pr} `{short_repo}` PR #{pr_num} "
                f"| {bv} | {m.get('status', '?')}"
            )

    lines.append("")
    lines.append(f"🕐 *Sync:* `{s.get('last_session_sync', '?')[:19]}`")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI entrypoint — `python -m src.utils.state_manager status|pause|resume|snapshot`
# --------------------------------------------------------------------------- #
def _cli() -> int:
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        s = read_state()
        print(json.dumps(s, indent=2, default=str))
        return 0
    if cmd == "snapshot":
        print(snapshot())
        return 0
    if cmd == "pause":
        changed = pause()
        print("PAUSED" if changed else "already paused")
        return 0
    if cmd == "resume":
        changed = resume()
        print("RESUMED" if changed else "already running")
        return 0
    if cmd == "init":
        write_state(DEFAULT_STATE)
        print("state.json initialized")
        return 0

    print(f"unknown command: {cmd}")
    print("usage: python -m src.utils.state_manager [status|snapshot|pause|resume|init]")
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
