"""
from typing import Any
Review handler — processes /submit /reject /modify commands.

When the user comments on a GitHub Issue with:
  /submit          → marks finding as ready for manual submission
  /reject <reason> → discards the finding
  /modify <note>   → requests re-analysis with user's note

This handler parses the comment and returns an action dict.
The review-bot.yml workflow uses this to update state + reply.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


from src.utils.logger import get_logger
from src.utils.state import State

log = get_logger("review_handler")


class ReviewHandler:
    """Parses reviewer commands and updates state."""

    def process_comment(
        self,
        comment: str,
        commenter: str,
        issue_number: int,
    ) -> dict[str, Any]:
        """Process a GitHub Issue comment.

        Returns action dict with:
          - status: approved | rejected | modified | ignored
          - action: submit | reject | modify | noop
          - summary: human-readable summary
        """
        comment = comment.strip()
        cmd = comment.lower()

        if cmd.startswith("/submit"):
            return self._handle_submit(comment, commenter, issue_number)
        if cmd.startswith("/reject"):
            return self._handle_reject(comment, commenter, issue_number)
        if cmd.startswith("/modify"):
            return self._handle_modify(comment, commenter, issue_number)
        if cmd.startswith("/resolve"):
            return self._handle_resolve(comment, commenter, issue_number)

        return {
            "status": "ignored",
            "action": "noop",
            "summary": f"Unrecognized command from @{commenter}",
        }

    def _handle_submit(self, comment: str, commenter: str, issue: int) -> dict[str, Any]:
        parts = comment.split(maxsplit=1)
        note = parts[1].strip() if len(parts) > 1 else ""

        # Update state
        state = State("submissions")
        state.add(
            key=f"issue-{issue}",
            data={"status": "approved", "commenter": commenter, "note": note},
            status="approved",
        )

        return {
            "status": "approved",
            "action": "submit",
            "commenter": commenter,
            "issue": issue,
            "note": note,
            "summary": f"✅ @{commenter} approved submission. Manual submission required.",
        }

    def _handle_reject(self, comment: str, commenter: str, issue: int) -> dict[str, Any]:
        parts = comment.split(maxsplit=1)
        reason = parts[1].strip() if len(parts) > 1 else "No reason"

        state = State("submissions")
        state.add(
            key=f"issue-{issue}",
            data={"status": "rejected", "commenter": commenter, "reason": reason},
            status="rejected",
        )

        return {
            "status": "rejected",
            "action": "reject",
            "commenter": commenter,
            "issue": issue,
            "reason": reason,
            "summary": f"❌ @{commenter} rejected: {reason}",
        }

    def _handle_modify(self, comment: str, commenter: str, issue: int) -> dict[str, Any]:
        parts = comment.split(maxsplit=2)
        if len(parts) < 3:
            return {
                "status": "error",
                "action": "noop",
                "summary": "❌ /modify requires instructions. Usage: /modify <instructions>",
            }
        instructions = parts[2].strip()

        state = State("submissions")
        state.add(
            key=f"issue-{issue}",
            data={"status": "modify", "commenter": commenter, "instructions": instructions},
            status="modify",
        )

        return {
            "status": "modified",
            "action": "modify",
            "commenter": commenter,
            "issue": issue,
            "instructions": instructions,
            "summary": f"📝 @{commenter} requested modification: {instructions}",
        }

    def _handle_resolve(self, comment: str, commenter: str, issue: int) -> dict[str, Any]:
        """Handle /resolve — user fixed an operator-needed issue."""
        parts = comment.split(maxsplit=2)
        note = parts[2].strip() if len(parts) > 2 else (parts[1].strip() if len(parts) > 1 else "fixed")

        return {
            "status": "resolved",
            "action": "resolve",
            "commenter": commenter,
            "issue": issue,
            "note": note,
            "summary": f"✅ @{commenter} resolved: {note}. Bot will retry on next run.",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Process a reviewer comment")
    parser.add_argument("--comment", required=True)
    parser.add_argument("--commenter", required=True)
    parser.add_argument("--issue", required=True, type=int)
    args = parser.parse_args()

    handler = ReviewHandler()
    result = handler.process_comment(args.comment, args.commenter, args.issue)

    Path("state/review_result.json").parent.mkdir(parents=True, exist_ok=True)
    Path("state/review_result.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") != "ignored" else 1


if __name__ == "__main__":
    sys.exit(main())
