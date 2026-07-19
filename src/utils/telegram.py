"""
Telegram bot notifier with dual-engine telemetry architecture.

Engine 1 — Mutating Pinned HUD (Scoreboard):
    A single message (tracked by tg_master_hud_message_id in state.json)
    that is updated in-place via editMessageText on every cycle tick.
    Displays live pending USD assets, active PRs, and pipeline status.

Engine 2 — Event-Driven Broadcaster (Lifecycle Cards):
    Independent channel messages reserved exclusively for high-level
    system mutations (PR status changes, strategy shifts, self-healing).
    Each card includes inline [🛑 Emergency Stop] / [▶️ Resume Flow] buttons.

Backward Compatibility:
    All existing methods (send_pipeline_start, send_finding, send_pr_submission,
    etc.) remain unchanged. The HUD engine is additive — it does not replace
    existing event notifications, it supplements them by providing a clean,
    always-up-to-date scoreboard that replaces the noisy send_state_heartbeat().

Setup:
1. Create a bot via @BotFather on Telegram → get BOT_TOKEN
2. Send /start to your bot → get CHAT_ID via getUpdates
3. Add as GitHub Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from src.utils.logger import get_logger
from src.utils.retry import retry_network
from src.utils.sanitizer import sanitize

log = get_logger("telegram")


class TelegramNotifier:
    """Telegram Bot API client with dual-engine telemetry."""

    BASE_URL = "https://api.telegram.org"

    def __init__(self, token: str | None = None, chat_id: str | None = None):
        # Strip ALL whitespace from token (including internal if any)
        raw_token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.token = "".join(raw_token.split())  # remove ALL whitespace

        # Clean chat_id: remove spaces (Telegram displays ID with spaces)
        # BUT preserve the leading minus sign — channel IDs start with -100
        raw_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        cleaned = "".join(raw_chat_id.split())
        if cleaned.startswith("-"):
            self.chat_id = "-" + "".join(c for c in cleaned[1:] if c.isdigit())
        else:
            self.chat_id = "".join(c for c in cleaned if c.isdigit())

        self._dry_run = not self.token or not self.chat_id
        self._bot_username = ""
        self._hud_message_id: int | None = None

        if self._dry_run:
            log.info("Telegram in DRY-RUN mode (no TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
            return

        log.info(
            "Telegram: token length=%d, chat_id length=%d, chat_id starts=%s ends=%s",
            len(self.token), len(self.chat_id),
            self.chat_id[:4] if len(self.chat_id) >= 4 else "?",
            self.chat_id[-4:] if len(self.chat_id) >= 4 else "?",
        )

        self._verify_token()
        self._load_hud_message_id()

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
        """Call getUpdates to find what chat_ids this bot can see."""
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
                    log.error("FIX: Open https://api.telegram.org/bot<TOKEN>/getUpdates in browser")
                    log.error(
                        "FIX: Copy the chat_id from the response (the one starting with %s...)",
                        str(list(chat_ids)[0][0])[:6] if chat_ids else "??????",
                    )
                    log.error("FIX: Update TELEGRAM_CHAT_ID secret with that EXACT number")
            else:
                log.error("Telegram getUpdates failed: %d", resp.status_code)
        except Exception as exc:
            log.error("Telegram getUpdates error: %s", exc)

    # ────────────────────────────────────────────────────────────────── #
    # HUD Message ID persistence (state.json)
    # ────────────────────────────────────────────────────────────────── #

    def _load_hud_message_id(self) -> None:
        """Load the master HUD message ID from state.json."""
        try:
            state_path = Path("state.json")
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                hud_id = state.get("tg_master_hud_message_id")
                if hud_id and isinstance(hud_id, int):
                    self._hud_message_id = hud_id
                    log.info("Telegram HUD message ID loaded: %d", hud_id)
        except Exception as exc:
            log.warning("Could not load HUD message ID: %s", exc)

    def _save_hud_message_id(self, message_id: int) -> None:
        """Persist the master HUD message ID to state.json."""
        try:
            state_path = Path("state.json")
            state = {}
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding="utf-8"))
            state["tg_master_hud_message_id"] = message_id
            state["tg_hud_updated_at"] = datetime.now(UTC).isoformat()
            state_path.write_text(
                json.dumps(state, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            self._hud_message_id = message_id
            log.debug("Telegram HUD message ID saved: %d", message_id)
        except Exception as exc:
            log.warning("Could not save HUD message ID: %s", exc)

    @property
    def is_configured(self) -> bool:
        return not self._dry_run

    # ------------------------------------------------------------------ #
    # Inline keyboard — User Brake System (agent.md §2)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _control_keyboard(force_resume: bool = False) -> dict:
        """Build the inline keyboard with [🛑 Emergency Stop] and
        [▶️ Resume Flow] buttons."""
        if force_resume:
            return {
                "inline_keyboard": [[
                    {"text": "▶️ Resume Flow", "callback_data": "resume_system"},
                ]]
            }
        return {
            "inline_keyboard": [[
                {"text": "🛑 Emergency Stop", "callback_data": "pause_system"},
                {"text": "▶️ Resume Flow", "callback_data": "resume_system"},
            ]]
        }

    # ------------------------------------------------------------------ #
    # Core send (Engine 2: Event-Driven Broadcaster)
    # ------------------------------------------------------------------ #

    @retry_network(max_attempts=2, base_delay=1.0, max_delay=5.0)
    def send(
        self,
        text: str,
        parse_mode: str = "Markdown",
        with_controls: bool = False,
    ) -> bool:
        """Send a NEW text message to Telegram (lifecycle event card).

        This is Engine 2 — use for high-level system mutations only.
        For routine status updates, use update_master_hud() instead.
        """
        text = sanitize(text, max_len=4000)

        if self._dry_run:
            log.info("[TG-DRY] %s", text[:100])
            return False

        import httpx

        url = f"{self.BASE_URL}/bot{self.token}/sendMessage"
        payload: dict = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if with_controls:
            payload["reply_markup"] = self._control_keyboard()

        try:
            resp = httpx.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                log.debug("Telegram message sent: %s", text[:80])
                return True

            try:
                err_data = resp.json()
                err_desc = err_data.get("description", resp.text[:200])
            except Exception:
                err_desc = resp.text[:200]

            if resp.status_code == 403:
                log.error("Telegram 403: %s", err_desc)
                self._log_available_chat_ids()
            else:
                log.error("Telegram send failed: %d %s", resp.status_code, err_desc)

            return False
        except Exception as exc:
            log.error("Telegram send error: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # HUD Engine (Engine 1: Mutating Pinned Scoreboard)
    # ------------------------------------------------------------------ #

    @retry_network(max_attempts=2, base_delay=1.0, max_delay=5.0)
    def edit_message_text(
        self,
        text: str,
        message_id: int | None = None,
        parse_mode: str = "Markdown",
    ) -> bool:
        """Edit an existing message in-place via editMessageText API.

        This is the core of Engine 1 — the Mutating Pinned HUD.
        If message_id is None, uses the stored HUD message ID.
        If no HUD message exists, falls back to send() (creates a new message).
        """
        target_msg_id = message_id or self._hud_message_id
        text = sanitize(text, max_len=4000)

        if self._dry_run:
            log.info("[TG-DRY-HUD] %s", text[:100])
            return False

        if target_msg_id is None:
            log.info("No HUD message ID — falling back to send() for initial HUD")
            return self._send_and_pin_hud(text, parse_mode)

        import httpx

        url = f"{self.BASE_URL}/bot{self.token}/editMessageText"
        payload: dict = {
            "chat_id": self.chat_id,
            "message_id": target_msg_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            resp = httpx.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                log.debug("Telegram HUD updated (msg %d)", target_msg_id)
                return True

            try:
                err_data = resp.json()
                err_desc = err_data.get("description", resp.text[:200])
            except Exception:
                err_desc = resp.text[:200]

            # If message is gone or can't be edited, create a new one
            if resp.status_code == 400 and "message is not modified" in err_desc.lower():
                log.debug("Telegram HUD: content unchanged — skipping")
                return True

            if resp.status_code in (400, 404):
                log.warning("Telegram HUD message %d lost — creating new one", target_msg_id)
                self._hud_message_id = None
                return self._send_and_pin_hud(text, parse_mode)

            log.error("Telegram editMessageText failed: %d %s", resp.status_code, err_desc)
            return False
        except Exception as exc:
            log.error("Telegram editMessageText error: %s", exc)
            return False

    def _send_and_pin_hud(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a new message and store its ID as the HUD message.

        Also attempts to pin the message to the channel.
        """
        import httpx

        if self._dry_run:
            log.info("[TG-DRY-HUD-INIT] %s", text[:100])
            return False

        # Send the message
        url = f"{self.BASE_URL}/bot{self.token}/sendMessage"
        payload: dict = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            resp = httpx.post(url, json=payload, timeout=15)
            if resp.status_code != 200:
                log.error("Telegram HUD send failed: %d", resp.status_code)
                return False

            result = resp.json().get("result", {})
            msg_id = result.get("message_id")
            if not msg_id:
                log.error("Telegram HUD: no message_id in response")
                return False

            self._save_hud_message_id(msg_id)
            log.info("Telegram HUD message created: %d", msg_id)

            # Attempt to pin (non-blocking — pinning may fail if bot lacks admin rights)
            try:
                pin_url = f"{self.BASE_URL}/bot{self.token}/pinChatMessage"
                pin_resp = httpx.post(pin_url, json={
                    "chat_id": self.chat_id,
                    "message_id": msg_id,
                    "disable_notification": True,
                }, timeout=10)
                if pin_resp.status_code == 200:
                    log.info("Telegram HUD message pinned ✅")
                else:
                    log.info("Telegram HUD pin failed (%d) — not critical", pin_resp.status_code)
            except Exception:
                pass  # Pinning is optional

            return True
        except Exception as exc:
            log.error("Telegram HUD send error: %s", exc)
            return False

    def update_master_hud(
        self,
        pending_usd: int = 0,
        pending_prs: int = 0,
        merged_usd: int = 0,
        merged_count: int = 0,
        active_platforms: str = "",
        pipeline_status: str = "IDLE",
        last_action: str = "",
    ) -> bool:
        """Update the master HUD scoreboard with current operational state.

        This replaces the noisy send_state_heartbeat() — instead of sending
        a new message every cycle, it edits the pinned HUD message in-place.

        Args:
            pending_usd: Total real USD pending in open PRs
            pending_prs: Number of open PRs awaiting review
            merged_usd: Total real USD earned from merged PRs
            merged_count: Number of merged PRs
            active_platforms: Comma-separated list of active platforms
            pipeline_status: Current pipeline status (RUNNING/IDLE/PAUSED)
            last_action: Brief description of last action taken
        """
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        status_emoji = {
            "RUNNING": "🟢",
            "IDLE": "⚪",
            "PAUSED": "🔴",
            "HUNTING": "🎯",
            "BUILDING": "🔨",
        }.get(pipeline_status, "⚪")

        hud_text = (
            f"📊 *Bounty Hunter — Live Dashboard*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{status_emoji} *Status:* `{pipeline_status}`\n"
            f"🕐 *Updated:* {now}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Real USD Earned:* `${merged_usd}`\n"
            f"📦 *Merged PRs:* {merged_count}\n"
            f"⏳ *Pending USD:* `${pending_usd}`\n"
            f"🔍 *Open PRs:* {pending_prs}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

        if active_platforms:
            hud_text += f"🌐 *Active:* {active_platforms}\n"
        if last_action:
            hud_text += f"⚡ *Last:* {last_action[:60]}\n"

        hud_text += "━━━━━━━━━━━━━━━━━━\n"
        hud_text += "_Auto-updated each cycle · Tap controls below_"

        return self.edit_message_text(hud_text)

    # ------------------------------------------------------------------ #
    # Lifecycle event methods (Engine 2: Event-Driven Broadcaster)
    # These remain unchanged for backward compatibility.
    # ------------------------------------------------------------------ #

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
        msg += "\nReview on GitHub → `/submit` or `/reject`"
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
        msg += "━━━━━━━━━━━━━━━━━━\n"
        msg += "_Analyzing codebase for vulnerabilities..._"
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
        msg += "━━━━━━━━━━━━━━━━━━\n"
        msg += "_Golden Rules active — spam filtered_"
        self.send(msg)

    def send_pr_submission(
        self,
        repo: str,
        pr_url: str,
        pr_number: str,
        fix_description: str,
        bounty_value: str = "",
    ) -> None:
        """Category 3: 🚀 PR SUBMISSION — when a genuine fix is submitted.
        Includes inline [Emergency Stop] / [Resume Flow] buttons (agent.md §2)."""
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
        msg += "━━━━━━━━━━━━━━━━━━\n"
        msg += "_Waiting for maintainer review..._"
        self.send(msg, with_controls=True)

    def send_success_payout(
        self,
        repo: str,
        pr_number: str,
        action: str,
        bounty_value: str = "",
    ) -> None:
        """Category 4: 🎉 SUCCESS — when PR gets reviewed, approved, or merged.
        Includes inline [Emergency Stop] / [Resume Flow] buttons (agent.md §2)."""
        if action.lower() == "merged":
            emoji = "🎉"
            title = "PR MERGED!"
            payout_note = "💰 *Bounty payout processing!*"
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
        msg += "━━━━━━━━━━━━━━━━━━"
        self.send(msg, with_controls=True)

    # ------------------------------------------------------------------ #
    # System-level alerts (operator brake + heartbeat)
    # ------------------------------------------------------------------ #

    def send_system_paused(self, reason: str = "Operator triggered Emergency Stop") -> None:
        """Sent when system_status flips to PAUSED."""
        msg = (
            f"🛑 *SYSTEM PAUSED*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📝 *Reason:* {reason}\n"
            f"⏸️ *All hunting cycles halted.*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"_Tap Resume to continue._"
        )
        self.send(msg, with_controls=True)

    def send_system_resumed(self) -> None:
        """Sent when system_status flips back to RUNNING."""
        msg = (
            "▶️ *SYSTEM RESUMED*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🤖 *Hunting cycles re-activated.*\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        self.send(msg, with_controls=True)

    def send_state_heartbeat(self) -> None:
        """Periodic state snapshot — NOW UPDATES THE HUD instead of sending
        a new message. Falls back to send() if no HUD exists yet.

        This method is preserved for backward compatibility with existing
        workflow calls (pr-monitor.yml). It now delegates to update_master_hud()
        instead of creating a new message each time.
        """
        try:
            from src.utils import state_manager

            # Gather live metrics from state — ONLY active, real-asset entries
            state = state_manager.read_state()
            monitors = state.get("active_monitors", {})

            pending_usd = 0.0
            pending_prs = 0
            merged_usd = 0.0
            merged_count = 0
            active_platforms_set: set[str] = set()

            # Rejected platforms — virtual credits, never counted in USD totals
            VIRTUAL_CREDIT_PLATFORMS = {"mergeos", "internal_mrg"}

            for repo, monitor in monitors.items():
                status = str(monitor.get("status", "")).upper()
                bounty_val = str(monitor.get("bounty_value", ""))
                platform = str(monitor.get("platform", "")).lower()

                # Skip virtual-credit platforms entirely (never count in USD)
                is_virtual = any(vc in platform or vc in repo.lower() for vc in VIRTUAL_CREDIT_PLATFORMS)

                # Extract real USD amount from bounty_value
                # Matches: "$100", "$50 USD", "$150 USD (real Stripe escrow via Opire)"
                usd_amount = 0.0
                if "$" in bounty_val and not is_virtual:
                    import re
                    usd_match = re.search(r'\$(\d+(?:\.\d+)?)', bounty_val)
                    if usd_match:
                        usd_amount = float(usd_match.group(1))

                if status == "MERGED" and not is_virtual:
                    merged_count += 1
                    merged_usd += usd_amount
                elif status in ("UNDER_REVIEW", "PR_SUBMITTED") and not is_virtual:
                    pending_prs += 1
                    pending_usd += usd_amount

                if platform and not is_virtual:
                    # Clean up platform name for display
                    display_platform = platform.split("(")[0].strip()
                    if display_platform:
                        active_platforms_set.add(display_platform)

            pipeline_status = "PAUSED" if state.get("system_status", "").upper() == "PAUSED" else "RUNNING"
            last_action = state.get("current_execution_pointer", {}).get("last_action", "")

            self.update_master_hud(
                pending_usd=int(pending_usd),
                pending_prs=pending_prs,
                merged_usd=int(merged_usd),
                merged_count=merged_count,
                active_platforms=", ".join(sorted(active_platforms_set)) if active_platforms_set else "none",
                pipeline_status=pipeline_status,
                last_action=last_action,
            )
        except Exception as exc:
            log.error("Telegram heartbeat/HUD update failed: %s", exc)
            # Fallback: try a simple send
            try:
                from src.utils import state_manager
                snapshot_text = state_manager.snapshot()
            except Exception:
                snapshot_text = "_state unavailable_"
            msg = (
                f"💓 *STATE HEARTBEAT (fallback)*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{snapshot_text}\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            self.send(msg, with_controls=True)


# Singleton
_notifier: TelegramNotifier | None = None


def get_notifier() -> TelegramNotifier:
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier
