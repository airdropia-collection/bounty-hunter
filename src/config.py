"""
Bounty Hunter Configuration.

Reads from environment variables / GitHub Secrets. Validates at startup
and uses ``wake_operator()`` to notify the user if critical secrets
are missing.
"""
from __future__ import annotations

import os
from typing import List

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
        self.MAX_BOUNTIES_PER_RUN: int = int(os.getenv("MAX_BOUNTIES_PER_RUN", "5"))
        self.MIN_PAYOUT_USD: int = int(os.getenv("MIN_PAYOUT_USD", "500"))
        self.MAX_CONTEST_DAYS: int = int(os.getenv("MAX_CONTEST_DAYS", "30"))

        # === AI settings ===
        self.ENABLE_DOUBT_REVIEW: bool = os.getenv("ENABLE_DOUBT_REVIEW", "true").lower() == "true"
        self.AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "8192"))

        # === Logging ===
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT: str = os.getenv("LOG_FORMAT", "rich")

        # === Run mode ===
        self.DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"

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

    def missing_critical_secrets(self) -> List[str]:
        """Return list of critical missing secrets (would block operation)."""
        missing = []
        if not self.has_gemini:
            missing.append("GEMINI_API_KEY")
        if not self.has_groq:
            missing.append("GROQ_API_KEY")
        if not self.has_github:
            missing.append("GH_PAT + GH_REPO")
        return missing

    def missing_optional_secrets(self) -> List[str]:
        """Return list of optional missing secrets (degraded but functional)."""
        missing = []
        if not self.has_etherscan:
            missing.append("ETHERSCAN_API_KEY (needed for contract source fetching)")
        if not self.has_wallet:
            missing.append("WALLET_ADDRESS (needed to receive payouts)")
        return missing


# Singleton — created at import time with current env
CONFIG = Config()
