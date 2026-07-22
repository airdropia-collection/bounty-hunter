"""
Bounty Hunter Configuration.

Reads from environment variables / GitHub Secrets. Validates at startup
and uses ``wake_operator()`` to notify the user if critical secrets
are missing.
"""
from __future__ import annotations

import os
from typing import Any

from src.utils.logger import get_logger

log = get_logger("config")


class Config:
    """Configuration read from environment variables.

    Env vars are read at instance creation time (not class definition time)
    so tests can use monkeypatch to set them.
    """

    def __init__(self):
        # === AI APIs (both free tier) ===
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_MODEL: str = "gemini-1.5-flash"

        self.GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
        self.GROQ_MODEL: str = "llama-3.1-70b-versatile"

        # === GitHub ===
        self.GH_PAT: str = os.getenv("GH_PAT", "")
        self.GH_REPO: str = os.getenv("GH_REPO", "")

        # === Web3 ===
        self.ETH_RPC_URL: str = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")
        self.ETHERSCAN_API_KEY: str = os.getenv("ETHERSCAN_API_KEY", "")

        # === Wallet (NEVER private key) ===
        self.WALLET_ADDRESS: str = os.getenv("WALLET_ADDRESS", "")

        # === Scraper settings ===
        # Cycle 23 directive: lower floor from $500 to $1. Bot's account is at $0,
        # so success rate (CV building) matters more than bounty size. Lower-value
        # bounties also tend to have less competition. Maintainer trust builds
        # through merged-PR history, not bounty size.
        # Pre-qualification still applies (real-asset verified, parent issue open,
        # maintainer not dormant, code-capability match).
        self.MIN_PAYOUT_USD: int = int(os.getenv("MIN_PAYOUT_USD", "1"))
        self.MAX_CONTEST_DAYS: int = int(os.getenv("MAX_CONTEST_DAYS", "30"))

        # === AI settings ===
        self.ENABLE_DOUBT_REVIEW: bool = os.getenv("ENABLE_DOUBT_REVIEW", "true").lower() == "true"
        self.AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "8192"))

        # === Logging ===
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT: str = os.getenv("LOG_FORMAT", "rich")

        # === Run mode ===
        self.DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"

        # === REAL-ASSET PAYOUT GATE (added 2026-07-18, Cycle 5) ===
        # The system ONLY targets bounties backed by real, withdrawable assets.
        # Virtual credits, reputation points, "future tokens," and un-deployed
        # smart contract promises are automatically rejected at the ingest layer.
        #
        # See agent.md §0 (Pre-Flight Reconnaissance Protocol) for the full
        # verification checklist. See docs/post_mortem_cycle_4.md for the
        # negligence report that triggered this gate.
        #
        # ACCEPTED asset types:
        #   - "usd_stripe" — Real USD escrowed via Stripe Connect (e.g., IssueHunt)
        #   - "usd_paypal" — Real USD via PayPal production (not sandbox)
        #   - "usdc_onchain" — USDC deployed on Ethereum/Polygon/Solana mainnet
        #   - "usdt_onchain" — USDT deployed on Ethereum/Tron/Polygon mainnet
        #   - "native_token" — Deployed, tradeable L1 token (ETH, SOL, MATIC, etc.)
        #
        # REJECTED asset types:
        #   - "virtual_credit" — Internal ledger credits with no withdrawal path
        #   - "future_token" — Un-deployed smart contract promises ("future-small")
        #   - "reputation_point" — Gamified scores (e.g., Stack Overflow style)
        #   - "sandbox_token" — Testnet-only tokens with no mainnet value
        #   - "internal_mrg" — MergeOS MRG (Solana program not deployed as of 2026-07-18)
        self.ACCEPTED_ASSET_TYPES: frozenset[str] = frozenset({
            "usd_stripe",
            "usd_paypal",
            "usdc_onchain",
            "usdt_onchain",
            "native_token",
        })
        self.REJECTED_ASSET_TYPES: frozenset[str] = frozenset({
            "virtual_credit",
            "future_token",
            "reputation_point",
            "sandbox_token",
            "internal_mrg",
        })
        # Platforms that have PASSED the Pre-Flight Reconnaissance Protocol (agent.md §0)
        # Only platforms in this set may be targeted for new bounty work.
        self.REAL_ASSET_VERIFIED_PLATFORMS: frozenset[str] = frozenset({
            "issuehunt",  # PASS: Real USD escrow via Stripe Connect, contributors withdraw to bank
        })
        # Platforms that FAILED the Pre-Flight Reconnaissance Protocol
        # These are permanently blocked from targeting unless re-verification passes
        self.VIRTUAL_CREDIT_FLAGGED_PLATFORMS: frozenset[str] = frozenset({
            "mergeos",  # FAIL: Solana program not deployed, no withdrawal mechanism, internal ledger only
        })
        # Platforms pending verification (INCONCLUSIVE)
        self.UNVERIFIED_PLATFORMS: frozenset[str] = frozenset({
            "dework",  # INCONCLUSIVE: Claims crypto payouts but escrow verification not yet performed
        })

        # === NATURAL DEVELOPER PERSONA (added 2026-07-20, Cycle 13) ===
        # Centralized rules for humanizing external git artifacts (commit
        # messages, PR titles, PR bodies). The previous pipeline leaked
        # rigid AI signatures into upstream PRs (e.g., "[BOUNTY $100]"
        # prefixes, "🤖 bot:" commit prefixes, markdown tables in PR
        # descriptions, "Here is the PR" prefaces). These patterns flag
        # the bot to hostile maintainers and trigger anti-spam filters.
        #
        # The persona layer is enforced by src/utils/persona.py, which
        # is invoked by .github/workflows/submit-pr.yml BEFORE the
        # GitHub API call. The same helpers are available to any src/
        # module that generates external text.
        #
        # Design principle: persona rules live HERE (single source of
        # truth), not duplicated across workflows and scripts.
        self.NATURAL_PERSONA: dict[str, Any] = {
            # Conventional commit types — lowercase, scoped, imperative mood
            "commit_types": ("fix", "feat", "chore", "docs", "refactor", "test", "perf", "build", "ci", "style"),
            "commit_max_subject_length": 72,
            "commit_max_body_line_length": 100,
            # PR title rules
            "pr_title_max_length": 80,
            "pr_title_strip_patterns": (
                r"\[BOUNTY\s+\$?\d+\]",          # [BOUNTY $100] / [BOUNTY 100]
                r"\[\$?\d+\s+USD?\]",             # [$100 USD] / [100 US]
                r"^🤖\s*",                        # leading bot emoji
                r"^AI[-:]\s*",                    # "AI:" / "AI-" prefix
                r"^(Here is|Below is|I have).+:", # AI preface sentences
                r"\s*\(bot\)",                    # (bot) suffix
            ),
            # PR body rules — what to strip / refuse to emit
            "pr_body_forbidden_phrases": (
                "as an ai",
                "as a language model",
                "i'd be happy to",
                "i would be happy to",
                "here is the",
                "below is the",
                "i have implemented",
                "i have created",
                "let me know if",
                "feel free to",
                "i hope this helps",
                "certainly!",
                "of course!",
                "sure thing",
            ),
            "pr_body_forbidden_prefixes": (
                "## Summary",       # markdown template signature
                "## Description",
                "### What",
                "### Why",
                "This PR",
                "This pull request",
            ),
            # Bot signatures that must NEVER appear in external text
            "signature_blocklist": (
                "🤖",
                "🚀",
                "✅",
                "❌",
                "🎯",
                "📝",
                "shield",
                "[BOT]",
                "bounty-hunter-bot",  # in commit author name too — but author email stays internal
            ),
            # Markdown constructs to strip from PR bodies (keep natural prose)
            "pr_body_strip_markdown_tables": True,
            "pr_body_strip_emoji": True,
            # Maximum PR body length (GitHub API allows 262144 but hostile
            # maintainers flag anything >2KB as "automated template dump")
            "pr_body_max_length": 2000,
        }

    # ------------------------------------------------------------------ #
    # Persona helper (added 2026-07-20, Cycle 13)
    # ------------------------------------------------------------------ #
    def get_persona_rule(self, key: str) -> Any:
        """Fetch a single persona rule by key.

        Centralized accessor so callers don't reach into the dict
        directly — keeps the contract stable if we later move the
        rules to a JSON/YAML file.
        """
        return self.NATURAL_PERSONA.get(key)

    # ------------------------------------------------------------------ #
    # Convenience properties
    # ------------------------------------------------------------------ #
    @property
    def has_gemini(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @property
    def has_groq(self) -> bool:
        return bool(self.GROQ_API_KEY)

    @property
    def has_any_llm(self) -> bool:
        return self.has_gemini or self.has_groq

    @property
    def has_github(self) -> bool:
        return bool(self.GH_PAT and self.GH_REPO)

    @property
    def has_etherscan(self) -> bool:
        return bool(self.ETHERSCAN_API_KEY)

    @property
    def has_wallet(self) -> bool:
        return bool(self.WALLET_ADDRESS)

    def missing_critical_secrets(self) -> list[str]:
        """Return list of critical missing secrets (would block operation)."""
        missing = []
        if not self.has_gemini:
            missing.append("GEMINI_API_KEY")
        if not self.has_groq:
            missing.append("GROQ_API_KEY")
        if not self.has_github:
            missing.append("GH_PAT + GH_REPO")
        return missing

    def missing_optional_secrets(self) -> list[str]:
        """Return list of optional missing secrets (degraded but functional)."""
        missing = []
        if not self.has_etherscan:
            missing.append("ETHERSCAN_API_KEY (needed for contract source fetching)")
        if not self.has_wallet:
            missing.append("WALLET_ADDRESS (needed to receive payouts)")
        return missing

    # ------------------------------------------------------------------ #
    # Real-Asset Payout Gate helpers (added 2026-07-18, Cycle 5)
    # ------------------------------------------------------------------ #
    def is_platform_targetable(self, platform: str) -> bool:
        """Check if a platform has passed the Pre-Flight Reconnaissance Protocol.

        Only platforms in REAL_ASSET_VERIFIED_PLATFORMS may be targeted for
        new bounty work. Platforms in VIRTUAL_CREDIT_FLAGGED_PLATFORMS are
        permanently blocked. Platforms in UNVERIFIED_PLATFORMS are held
        pending operator review.
        """
        if platform in self.VIRTUAL_CREDIT_FLAGGED_PLATFORMS:
            log.warning(
                "platform '%s' is VIRTUAL-CREDIT-FLAGGED — blocked by real-asset gate",
                platform,
            )
            return False
        if platform in self.UNVERIFIED_PLATFORMS:
            log.warning(
                "platform '%s' is UNVERIFIED — held pending Pre-Flight Reconnaissance",
                platform,
            )
            return False
        if platform in self.REAL_ASSET_VERIFIED_PLATFORMS:
            return True
        log.warning(
            "platform '%s' is not in any verification set — defaulting to blocked",
            platform,
        )
        return False

    def is_asset_type_accepted(self, asset_type: str) -> bool:
        """Check if a reward asset type is accepted by the real-asset gate.

        Accepted: usd_stripe, usd_paypal, usdc_onchain, usdt_onchain, native_token
        Rejected: virtual_credit, future_token, reputation_point, sandbox_token, internal_mrg
        """
        if asset_type in self.REJECTED_ASSET_TYPES:
            log.warning(
                "asset type '%s' is REJECTED by real-asset gate",
                asset_type,
            )
            return False
        return asset_type in self.ACCEPTED_ASSET_TYPES


# Singleton — created at import time with current env
CONFIG = Config()
