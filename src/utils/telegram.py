"""
Telegram bot notifier.

Sends live notifications to the user's Telegram.

Setup:
1. Create a bot via @BotFather on Telegram → get BOT_TOKEN
2. Send /start to your bot → get CHAT_ID via getUpdates
3. Add as GitHub Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
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
        # Strip ALL whitespace from token (including internal if any)
        raw_token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.token = "".join(raw_token.split())  # remove ALL whitespace

        # Clean chat_id: remove spaces (Telegram displays ID with spaces)
        # BUT preserve the leading minus sign — channel IDs start with -100
        # e.g. "-100 4123 4567 890" → "-10041234567890"
        raw_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        # Remove all whitespace, then ensure only digits and leading minus
        cleaned = "".join(raw_chat_id.split())  # remove all whitespace
        # Keep leading minus if present, then strip any non-digits after
        if cleaned.startswith("-"):
            self.chat_id = "-" + "".join(c for c in cleaned[1:] if c.isdigit())
        else:
            self.chat_id = "".join(c for c in cleaned if c.isdigit())

        self._dry_run = not self.token or not self.chat_id
        self._bot_username = ""

        if self._dry_run:
            log.info("Telegram in DRY-RUN mode (no TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
            return

        # Debug: log lengths (not actual values) for troubleshooting
        log.info(
            "Telegram: token length=%d, chat_id length=%d, chat_id starts=%s ends=%s",
            len(self.token), len(self.chat_id),
            self.chat_id[:4] if len(self.chat_id) >= 4 else "?",
            self.chat_id[-4:] if len(self.chat_id) >= 4 else "?",
        )

        # Verify bot token (getMe)
        self._verify_token()

    def _verify_token(self) -> None:
        """Verify bot token via getMe. Does NOT disable on failure."""
        import httpx

        try:
            resp = httpx.get(
                f"{self.BASE_URL}/bot{self.token}/getMe",
                timeout=10,
            )
            if resp.status_code == 200:
                bot_info = resp.json().get("result", {})
                self._bot_username = bot_info.get("username", "unknown")
                log.info("Telegram bot verified: @%s", self._bot_username)
            else:
                log.warning("Telegram: getMe failed (%d) — will retry on send", resp.status_code)
        except Exception as exc:
            log.warning("Telegram: getMe error: %s — will retry on send", exc)

    def _log_available_chat_ids(self) -> None:
        """Call getUpdates to find what chat_ids this bot can see.
        This helps debug 403 Forbidden errors."""
        import httpx

        try:
            resp = httpx.get(
                f"{self.BASE_URL}/bot{self.token}/getUpdates",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                updates = data.get("result", [])
                if not updates:
                    log.error(
                        "Telegram getUpdates: NO updates found. "
                        "User must send /start to bot @%s FIRST, "
                        "THEN get the chat_id.",
                        self._bot_username or "your_bot",
                    )
                    return

                chat_ids = set()
                for update in updates:
                    msg = update.get("message") or update.get("edited_message")
                    if msg:
                        chat = msg.get("chat", {})
                        cid = chat.get("id")
                        ctype = chat.get("type")
                        cuser = chat.get("first_name", "")
                        if cid:
                            chat_ids.add((cid, ctype, cuser))

                log.error(
                    "Telegram getUpdates: found %d chat(s) that sent messages to this bot:",
                    len(chat_ids),
                )
                for cid, ctype, cuser in chat_ids:
                    # Show first 6 + last 4 digits for easier identification
                    cid_str = str(cid)
                    if len(cid_str) > 10:
                        masked = cid_str[:6] + "..." + cid_str[-4:]
                    else:
                        masked = cid_str
                    log.error(
                        "  → chat_id=%s (type=%s, user=%s) — %s",
                        masked, ctype, cuser,
                        "✅ MATCHES your secret" if str(cid) == self.chat_id else "❌ does NOT match TELEGRAM_CHAT_ID",
                    )

                if not any(str(cid) == self.chat_id for cid, _, _ in chat_ids):
                    log.error(
                        "ROOT CAUSE: TELEGRAM_CHAT_ID=%s does NOT match any chat that messaged this bot!",
                        self.chat_id[:6] + "..." + self.chat_id[-4:] if len(self.chat_id) > 10 else self.chat_id,
                    )
                    log.error(
                        "FIX: Open https://api.telegram.org/bot<TOKEN>/getUpdates in browser"
                    )
                    log.error(
                        "FIX: Copy the chat_id from the response (the one starting with %s...)",
                        str(list(chat_ids)[0][0])[:6] if chat_ids else "??????",
                    )
                    log.error(
                        "FIX: Update TELEGRAM_CHAT_ID secret with that EXACT number"
                    )
            else:
                log.error("Telegram getUpdates failed: %d", resp.status_code)
        except Exception as exc:
            log.error("Telegram getUpdates error: %s", exc)

    @property
    def is_configured(self) -> bool:
        return not self._dry_run

    @retry_network(max_attempts=2, base_delay=1.0, max_delay=5.0)
    def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a text message to Telegram."""
        text = sanitize(text, max_len=4000)

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

        try:
            resp = httpx.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                log.debug("Telegram message sent: %s", text[:80])
                return True

            # Handle errors
            try:
                err_data = resp.json()
                err_desc = err_data.get("description", resp.text[:200])
            except Exception:
                err_desc = resp.text[:200]

            if resp.status_code == 403:
                # 403 = bot can't message this chat_id
                # Run diagnostic ONCE to show available chat_ids
                log.error("Telegram 403: %s", err_desc)
                self._log_available_chat_ids()
            else:
                log.error("Telegram send failed: %d %s", resp.status_code, err_desc)

            return False
        except Exception as exc:
            log.error("Telegram send error: %s", exc)
            return False

    def send_pipeline_start(self, platform: str, max_bounties: int) -> None:
        self.send(
            f"🤖 *Pipeline Started*\n"
            f"Platform: `{platform}`\n"
            f"Max bounties: {max_bounties}"
        )

    def send_pipeline_complete(
        self,
        total_bounties: int,
        total_findings: int,
        submittable: int,
    ) -> None:
        emoji = "🎯" if submittable > 0 else "✅"
        self.send(
            f"{emoji} *Pipeline Complete*\n"
            f"Bounties: {total_bounties}\n"
            f"Findings: {total_findings}\n"
            f"Verified: {submittable}"
        )

    def send_finding(
        self,
        project: str,
        title: str,
        severity: str,
        confidence: float,
        url: str = "",
    ) -> None:
        severity_emoji = {
            "Critical": "🔴",
            "High": "🟠",
            "Medium": "🟡",
            "Low": "🟢",
            "Info": "ℹ️",
        }.get(severity, "❓")

        msg = (
            f"{severity_emoji} *VERIFIED Finding: {project}*\n"
            f"Title: {title}\n"
            f"Severity: {severity}\n"
            f"Confidence: {confidence:.0%}\n"
        )
        if url:
            msg += f"[View bounty]({url})\n"
        msg += f"\nReview on GitHub → `/submit` or `/reject`"
        self.send(msg)

    def send_error(self, error: str, context: str = "") -> None:
        error = sanitize(error, max_len=500)
        msg = "❌ *Error*\n"
        if context:
            msg += f"Context: {context}\n"
        msg += f"```\n{error}\n```"
        self.send(msg)

    def send_operator_needed(self, title: str, issue_url: str = "") -> None:
        msg = "🚨 *OPERATOR NEEDED*\n" + title + "\n"
        if issue_url:
            msg += f"[Open Issue]({issue_url})\n"
        msg += "\nWake the AI operator in chat to resolve."
        self.send(msg)

    # ------------------------------------------------------------------ #
    # LIVE PULSE — 4 structured event categories
    # ------------------------------------------------------------------ #

    def send_scanning_event(
        self,
        repo: str,
        issue_title: str,
        bounty_value: str,
        tech_stack: str,
        issue_url: str = "",
    ) -> None:
        """Category 1: 🔍 SCANNING — when a new high-quality target is picked."""
        msg = (
            f"🔍 *SCANNING TARGET*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Repo:* `{repo}`\n"
            f"📝 *Issue:* {issue_title}\n"
            f"💰 *Bounty:* {bounty_value}\n"
            f"🔧 *Stack:* {tech_stack}\n"
        )
        if issue_url:
            msg += f"🔗 [View Issue]({issue_url})\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n"
        msg += f"_Analyzing codebase for vulnerabilities..._"
        self.send(msg)

    def send_filter_event(
        self,
        repo: str,
        reason: str,
        details: str = "",
    ) -> None:
        """Category 2: 🛡️ FILTER — when Golden Rules trigger and skip/close spam."""
        msg = (
            f"🛡️ *FILTER TRIGGERED*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Repo:* `{repo}`\n"
            f"⚠️ *Action:* {reason}\n"
        )
        if details:
            msg += f"📋 *Details:* {details}\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n"
        msg += f"_Golden Rules active — spam filtered_"
        self.send(msg)

    def send_pr_submission(
        self,
        repo: str,
        pr_url: str,
        pr_number: str,
        fix_description: str,
        bounty_value: str = "",
    ) -> None:
        """Category 3: 🚀 PR SUBMISSION — when a genuine fix is submitted."""
        msg = (
            f"🚀 *PR SUBMITTED*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Repo:* `{repo}`\n"
            f"🔀 *PR:* #{pr_number}\n"
            f"🔗 [View PR]({pr_url})\n"
            f"📝 *Fix:* {fix_description}\n"
        )
        if bounty_value:
            msg += f"💰 *Target:* {bounty_value}\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n"
        msg += f"_Waiting for maintainer review..._"
        self.send(msg)

    def send_success_payout(
        self,
        repo: str,
        pr_number: str,
        action: str,
        bounty_value: str = "",
    ) -> None:
        """Category 4: 🎉 SUCCESS — when PR gets reviewed, approved, or merged."""
        if action.lower() == "merged":
            emoji = "🎉"
            title = "PR MERGED!"
            payout_note = "💰 *Bounty payout may be processing on IssueHunt!*"
        elif action.lower() == "approved":
            emoji = "✅"
            title = "PR APPROVED!"
            payout_note = "⏳ *Awaiting merge — payout incoming!*"
        elif action.lower() == "reviewed":
            emoji = "👀"
            title = "PR UNDER REVIEW!"
            payout_note = "⏳ *Maintainer is reviewing — stay tuned!*"
        else:
            emoji = "📢"
            title = f"PR {action.upper()}!"
            payout_note = ""

        msg = (
            f"{emoji} *{title}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Repo:* `{repo}`\n"
            f"🔀 *PR:* #{pr_number}\n"
        )
        if bounty_value:
            msg += f"💰 *Bounty:* {bounty_value}\n"
        if payout_note:
            msg += f"\n{payout_note}\n"
        msg += f"━━━━━━━━━━━━━━━━━━"
        self.send(msg)


# Singleton
_notifier: TelegramNotifier | None = None


def get_notifier() -> TelegramNotifier:
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier
