"""
Startup health check.

Run as:
    python -m src.health

If critical secrets are missing, automatically calls ``wake_operator()``
to create a GitHub Issue notifying the user.

Exits 0 if everything OK, 1 if critical secrets missing.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from src.config import CONFIG
from src.utils.github_client import GitHubClient
from src.utils.logger import get_logger

log = get_logger("health")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "info"  # error | warning | info


def _check_llm_keys() -> list[Check]:
    checks = []
    if CONFIG.has_gemini:
        checks.append(Check("gemini_api_key", True, "Gemini API key present", "info"))
    else:
        checks.append(Check("gemini_api_key", False, "GEMINI_API_KEY not set", "error"))

    if CONFIG.has_groq:
        checks.append(Check("groq_api_key", True, "Groq API key present", "info"))
    else:
        checks.append(Check("groq_api_key", False, "GROQ_API_KEY not set (no AI fallback)", "warning"))

    if not CONFIG.has_any_llm:
        checks.append(Check("any_llm", False, "No AI keys — bot cannot function", "error"))
    else:
        checks.append(Check("any_llm", True, "At least one AI provider configured", "info"))
    return checks


def _check_github() -> Check:
    if CONFIG.has_github:
        return Check("github", True, f"GH_PAT + GH_REPO={CONFIG.GH_REPO}", "info")
    return Check("github", False, "GH_PAT or GH_REPO not set (no issue creation)", "error")


def _check_web3() -> list[Check]:
    checks = []
    if CONFIG.ETH_RPC_URL:
        checks.append(Check("eth_rpc", True, f"ETH_RPC_URL={CONFIG.ETH_RPC_URL}", "info"))
    else:
        checks.append(Check("eth_rpc", False, "ETH_RPC_URL not set", "warning"))

    if CONFIG.has_etherscan:
        checks.append(Check("etherscan", True, "Etherscan API key present", "info"))
    else:
        checks.append(Check("etherscan", False, "ETHERSCAN_API_KEY not set (can't fetch contract source)", "warning"))
    return checks


def _check_wallet() -> Check:
    if CONFIG.has_wallet:
        return Check("wallet", True, "Wallet address present", "info")
    return Check("wallet", False, "WALLET_ADDRESS not set (can't receive payouts yet)", "warning")


def _check_dry_run() -> Check:
    if CONFIG.DRY_RUN:
        return Check("dry_run", True, "DRY_RUN=true (safe mode, no real submissions)", "info")
    return Check("dry_run", True, "DRY_RUN=false (REAL submissions enabled — be careful!)", "warning")


def run_all_checks() -> list[Check]:
    checks: list[Check] = []
    checks.extend(_check_llm_keys())
    checks.append(_check_github())
    checks.extend(_check_web3())
    checks.append(_check_wallet())
    checks.append(_check_dry_run())
    return checks


def print_report(checks: list[Check]) -> int:
    has_error = False
    has_warning = False

    print("\n" + "=" * 60)
    print("  🩺 Bounty Hunter — Health Check")
    print("=" * 60)

    for c in checks:
        emoji = {"error": "❌", "warning": "⚠️ ", "info": "✅"}[c.severity]
        print(f"  {emoji} {c.name:20} {c.detail}")
        if c.severity == "error" and not c.ok:
            has_error = True
        if c.severity == "warning":
            has_warning = True

    print("=" * 60)
    if has_error:
        print("  ❌ ERRORS — bot cannot run. Fix and re-run.")
        code = 1
    elif has_warning:
        print("  ⚠️  WARNINGS — bot will run with degraded functionality.")
        code = 0
    else:
        print("  ✅ All checks passed — ready to hunt!")
        code = 0
    print("=" * 60 + "\n")
    return code


def wake_operator_if_needed(checks: list[Check]) -> None:
    """If critical secrets are missing, create a GitHub Issue to wake the operator."""
    errors = [c for c in checks if c.severity == "error" and not c.ok]
    if not errors:
        return

    gh = GitHubClient()
    if gh._dry_run:
        log.warning("cannot wake operator (no GitHub credentials) — errors:")
        for e in errors:
            log.warning("  - %s: %s", e.name, e.detail)
        return

    # Check if there's already an open operator-needed issue (don't spam)
    if gh.is_operator_needed():
        log.info("operator-needed Issue already open — not creating a new one")
        return

    error_list = "\n".join(f"- **{e.name}**: {e.detail}" for e in errors)
    gh.wake_operator(
        title="Critical secrets missing — bot cannot run",
        body=f"""The bounty-hunter bot tried to start but found these critical issues:

{error_list}

### How to fix
1. Go to https://github.com/{CONFIG.GH_REPO}/settings/secrets/actions
2. Add the missing secrets (see `.env.example` for what each one is)
3. Come back here and comment `/resolve fixed`
4. The bot will retry on the next scheduled run

### Where to get the keys
- **GEMINI_API_KEY**: https://aistudio.google.com/app/apikey (free, 1M tokens/day)
- **GROQ_API_KEY**: https://console.groq.com/ (free, 1M tokens/day)
- **GH_PAT**: https://github.com/settings/tokens (fine-grained, scoped to this repo)

After adding, comment `/resolve fixed` here.
""",
        category="missing_secret",
        context={"errors": [{"name": e.name, "detail": e.detail} for e in errors]},
    )
    log.info("woke operator — created GitHub Issue for missing secrets")


def main() -> int:
    log.info("Running health checks...")
    checks = run_all_checks()
    code = print_report(checks)
    if code == 1:
        wake_operator_if_needed(checks)
    return code


if __name__ == "__main__":
    sys.exit(main())
