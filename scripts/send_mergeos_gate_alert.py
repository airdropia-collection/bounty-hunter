"""Send MergeOS Gate 1 incident + prevention alert to Telegram."""
import json
import subprocess
import urllib.request

gh_pat = subprocess.check_output(
    ["bash", "-c",
     "git config --get remote.origin.url | "
     "sed -n 's|https://x-access-token:\\([^@]*\\)@.*|\\1|p'"],
    cwd="/home/z/my-project/bounty-hunter"
).decode().strip()

msg = (
    "🛡️ MERGEOS GATE 1 BLOCKED + PREVENTION DEPLOYED\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📦 PR #252: mergeos-bounties/Loru\n"
    "👤 Blocked by: @TUPM96 (maintainer)\n"
    "🔖 Commit: 2166e5d\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "🚨 INCIDENT:\n"
    "Bot submitted PR #252 without completing MergeOS Gate 1 (badges).\n"
    "Maintainer requires 3 community actions BEFORE PR review.\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🎯 YOUR 3 MANUAL ACTIONS (30 sec, browser only):\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "1️⃣ Follow the org:\n"
    "   https://github.com/mergeos-bounties\n"
    "   (Click 'Follow' button top-right)\n"
    "\n"
    "2️⃣ Star core repo #1:\n"
    "   https://github.com/mergeos-bounties/mergeos\n"
    "   (Click 'Star' button top-right)\n"
    "\n"
    "3️⃣ Star core repo #2:\n"
    "   https://github.com/mergeos-bounties/mergeos-contracts\n"
    "   (Click 'Star' button top-right)\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📝 AFTER COMPLETING — post this comment on PR #252:\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "PR URL: https://github.com/mergeos-bounties/Loru/pull/252\n"
    "\n"
    "Comment text (copy-paste ready) saved to:\n"
    "scripts/pr_252_response_comment.md\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🛡️ PREVENTION SYSTEM DEPLOYED:\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "✅ NEW: src/utils/platform_onboarding.py\n"
    "    Verifies follow+star BEFORE any PR submission\n"
    "✅ NEW: docs/platform_policies/mergeos.md\n"
    "    Full 4-gate policy documented (badges→security→tests→merge)\n"
    "✅ UPDATED: .github/workflows/submit-pr.yml\n"
    "    Added '🛡️ Platform Onboarding Gate' step\n"
    "    → Blocks PR submission if onboarding incomplete\n"
    "    → Emits 🛡️ FILTER Telegram alert with missing actions\n"
    "✅ UPDATED: agent.md §4 — Pre-PR checklist now includes onboarding gate\n"
    "✅ UPDATED: state.json — PR #252 marked NEEDS_REVISION\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "❌ PAT SCOPE LIMITATION:\n"
    "Bot's fine-grained PAT can't follow/star (HTTP 403).\n"
    "Requires Classic PAT with 'user:follow' + 'public_repo' scopes.\n"
    "Until PAT upgrade, these 3 actions need manual operator completion.\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "_Aage se kabhi aisa nahi hoga — har PR submission se pehle bot\n"
    "onboarding check karega, agar missing ho to PR block ho jayega._\n"
    "_Tap buttons below to control the bot._"
)

payload = json.dumps({
    "ref": "main",
    "inputs": {
        "message": msg,
        "parse_mode": "Markdown",
    },
})

req = urllib.request.Request(
    "https://api.github.com/repos/airdropia-collection/bounty-hunter/"
    "actions/workflows/notify.yml/dispatches",
    data=payload.encode(),
    headers={
        "Authorization": f"token {gh_pat}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    },
    method="POST",
)
resp = urllib.request.urlopen(req, timeout=15)
print(f"HTTP Status: {resp.status}")
print(f"\nTelegram alert dispatched.")
