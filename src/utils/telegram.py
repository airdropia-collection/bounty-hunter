"""
Telegram bot notifier.

Sends live notifications to the user's Telegram so they always know
what the bot is doing — without having to check GitHub Actions.

Setup:
1. Create a bot via @BotFather on Telegram → get BOT_TOKEN
2. Send a message to your bot → get CHAT_ID
3. Add as GitHub Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

Usage:
    from src.utils.telegram import TelegramNotifier
    tg = TelegramNotifier()
    tg.send("🎯 Pipeline started — scanning 323 bounties")
    tg.send_finding("LayerZero reentrancy found!", severity="High")
"""
from __future__ import annotations

import os

from src.utils.logger import get_logger
from src.utils.retry import retry_network
from src.utils.sanitizer import sanitize

log = get_logger("telegram")


class TelegramNotifier:
    """Telegram Bot API client for sending notifications."""

    BASE_URL = "https://api.telegram.org"

    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._dry_run = not self.token or not self.chat_id
        if self._dry_run:
            log.info("Telegram in DRY-RUN mode (no TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")

    @property
    def is_configured(self) -> bool:
        return not self._dry_run

    @retry_network(max_attempts=2, base_delay=1.0, max_delay=5.0)
    def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a text message to Telegram.

        Returns True if sent, False if dry-run or failed.
        """
        # Sanitize — no secrets in Telegram messages
        text = sanitize(text, max_len=4000)  # Telegram limit is 4096

        if self._dry_run:
            log.info("[TG-DRY] %s", text[:100])
            return False

        import httpx

        url = f"{self.BASE_URL}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        resp = httpx.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            log.error("Telegram send failed: %d %s", resp.status_code, resp.text[:200])
            return False

        log.debug("Telegram message sent: %s", text[:80])
        return True

    def send_pipeline_start(self, platform: str, max_bounties: int) -> None:
        """Notify: pipeline started."""
        self.send(
            f"🤖 *Pipeline Started*\n"
            f"Platform: `{platform}`\n"
            f"Max bounties: {max_bounties}\n"
            f"Mode: dry-run (safe)"
        )

    def send_pipeline_complete(
        self,
        total_bounties: int,
        total_findings: int,
        submittable: int,
    ) -> None:
        """Notify: pipeline completed."""
        emoji = "🎯" if submittable > 0 else "✅"
        self.send(
            f"{emoji} *Pipeline Complete*\n"
            f"Bounties scraped: {total_bounties}\n"
            f"Findings: {total_findings}\n"
            f"Submittable: {submittable}\n"
            f"{'⚠️ Findings need your review!' if submittable > 0 else 'No actionable findings.'}"
        )

    def send_finding(
        self,
        project: str,
        title: str,
        severity: str,
        confidence: float,
        url: str = "",
    ) -> None:
        """Notify: a vulnerability finding was found."""
        severity_emoji = {
            "Critical": "🔴",
            "High": "🟠",
            "Medium": "🟡",
            "Low": "🟢",
            "Info": "ℹ️",
        }.get(severity, "❓")

        msg = (
            f"{severity_emoji} *Finding: {project}*\n"
            f"Title: {title}\n"
            f"Severity: {severity}\n"
            f"Confidence: {confidence:.0%}\n"
        )
        if url:
            msg += f"[View bounty]({url})\n"
        msg += f"\nReview on GitHub Issues → `/submit` or `/reject`"
        self.send(msg)

    def send_error(self, error: str, context: str = "") -> None:
        """Notify: an error occurred."""
        error = sanitize(error, max_len=500)
        msg = f"❌ *Error*\n"
        if context:
            msg += f"Context: {context}\n"
        msg += f"```\n{error}\n```"
        self.send(msg)

    def send_operator_needed(self, title: str, issue_url: str = "") -> None:
        """Notify: operator (you) needs to take action."""
        msg = (
            f"🚨 *OPERATOR NEEDED*\n"
            f"{title}\n"
        )
        if issue_url:
            msg += f"[Open Issue]({issue_url})\n"
        msg += f"\nWake the AI operator in chat to resolve this."
        self.send(msg)


# Singleton
_notifier: TelegramNotifier | None = None


def get_notifier() -> TelegramNotifier:
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier
