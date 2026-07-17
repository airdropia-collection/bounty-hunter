"""
Telegram Callback Handler — processes inline button presses.

When the user taps [🛑 Emergency Stop] or [▶️ Resume Flow] on any
Telegram message, Telegram sends a callback_query to the bot. This
handler polls getUpdates, finds callback_query events, and updates
state.json accordingly (agent.md §2).

Run as a GitHub Action every 5 minutes (see telegram-handler.yml).

Usage:
    python -m src.utils.telegram_callback_handler
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from src.utils import state_manager
from src.utils.logger import get_logger
from src.utils.telegram import get_notifier

log = get_logger("callback_handler")

# Persist the last update_id we processed so we don't replay old callbacks.
# Stored INSIDE state.json (under "tg_callback_offset") so it persists via
# the existing commit workflow (the state/ directory is gitignored, so a
# separate offset file would be lost between runs).
OFFSET_KEY = "tg_callback_offset"


# --------------------------------------------------------------------------- #
# Offset persistence (stored inside state.json)
# --------------------------------------------------------------------------- #
def _load_offset() -> int:
    try:
        state = state_manager.read_state()
        return int(state.get(OFFSET_KEY, 0) or 0)
    except Exception:  # noqa: BLE001
        return 0


def _save_offset(offset: int) -> None:
    state = state_manager.read_state()
    state[OFFSET_KEY] = offset
    state_manager.write_state(state)


# --------------------------------------------------------------------------- #
# Telegram API helpers
# --------------------------------------------------------------------------- #
def _tg_request(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a Telegram Bot API method."""
    notifier = get_notifier()
    if not notifier.is_configured:
        log.warning("Telegram not configured — skipping callback handler")
        return {"ok": False, "error": "not_configured"}

    url = f"{notifier.BASE_URL}/bot{notifier.token}/{method}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.error("Telegram API %s failed: %s", method, exc)
        return {"ok": False, "error": str(exc)}


def _answer_callback(callback_id: str, text: str) -> None:
    """Answer a callback_query (this dismisses the loading spinner on
    the user's Telegram client and shows a small toast)."""
    _tg_request("answerCallbackQuery", {
        "callback_query_id": callback_id,
        "text": text,
        "show_alert": False,
    })


# --------------------------------------------------------------------------- #
# Main handler
# --------------------------------------------------------------------------- #
def handle_callbacks() -> int:
    """Poll Telegram getUpdates for callback_query events and process them.

    Returns the number of callbacks processed.
    """
    offset = _load_offset()
    log.info("polling Telegram getUpdates with offset=%d", offset)

    # getUpdates with a long-poll timeout; allow_updates filters to callback_query
    resp = _tg_request("getUpdates", {
        "offset": offset,
        "timeout": 5,
        "allowed_updates": ["callback_query"],
    })

    if not resp.get("ok"):
        log.error("getUpdates failed: %s", resp.get("description", resp))
        return 0

    updates = resp.get("result", [])
    if not updates:
        log.info("no new callbacks")
        return 0

    processed = 0
    new_offset = offset

    for update in updates:
        new_offset = max(new_offset, update.get("update_id", 0) + 1)
        cb = update.get("callback_query")
        if not cb:
            continue

        callback_id = cb.get("id", "")
        callback_data = cb.get("data", "")
        user = cb.get("from", {})
        username = user.get("username") or user.get("first_name", "unknown")

        log.info("callback: data=%s from=@%s", callback_data, username)

        if callback_data == "pause_system":
            changed = state_manager.pause()
            if changed:
                _answer_callback(callback_id, "🛑 System PAUSED — all hunting halted")
                notifier = get_notifier()
                notifier.send_system_paused(
                    reason=f"Operator @{username} tapped Emergency Stop"
                )
                log.warning("🛑 PAUSED by @%s", username)
            else:
                _answer_callback(callback_id, "System was already paused")
            processed += 1

        elif callback_data == "resume_system":
            changed = state_manager.resume()
            if changed:
                _answer_callback(callback_id, "▶️ System RESUMED — hunting re-activated")
                notifier = get_notifier()
                notifier.send_system_resumed()
                log.info("▶️ RESUMED by @%s", username)
            else:
                _answer_callback(callback_id, "System was already running")
            processed += 1

        else:
            log.warning("unknown callback_data: %s", callback_data)
            _answer_callback(callback_id, f"Unknown command: {callback_data}")

    _save_offset(new_offset)
    log.info("processed %d callback(s), new offset=%d", processed, new_offset)
    return processed


def main() -> int:
    """CLI entrypoint. Returns 0 on success, 1 on error."""
    try:
        n = handle_callbacks()
        log.info("callback handler complete — %d processed", n)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("callback handler crashed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
