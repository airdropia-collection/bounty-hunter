"""Send the PR-ready Telegram alert via the notify.yml workflow trigger."""
import json
import subprocess
import urllib.request

# Get PAT from git remote
gh_pat = subprocess.check_output(
    ["bash", "-c",
     "git config --get remote.origin.url | "
     "sed -n 's|https://x-access-token:\\([^@]*\\)@.*|\\1|p'"],
    cwd="/home/z/my-project/bounty-hunter"
).decode().strip()

# Construct the GitHub compare URL — opens the PR creation form pre-filled
compare_url = (
    "https://github.com/marcosgriselli/SwipeableTabBarController/compare/"
    "master...airdropia-collection:SwipeableTabBarController-1:"
    "fix/issue-52-quick-swipe-freeze?expand=1"
)

# Build the message — use code formatting instead of backticks to avoid bash issues
msg = (
    "🚀 PR BRANCH READY — One-Click Submission Needed\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📦 Repo: marcosgriselli/SwipeableTabBarController\n"
    "🔀 Branch: fix/issue-52-quick-swipe-freeze → master\n"
    "📝 Commit: 666a389\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "💰 Bounty: $150 (IssueHunt)\n"
    "⭐ Stars: 1,537 | 🔧 Swift / UIKit\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "🎯 Pre-PR Forensic Checks Passed:\n"
    "✅ Brace balance verified (0 diff)\n"
    "✅ Paren balance verified (0 diff)\n"
    "✅ Secret scan: 0 matches\n"
    "✅ No new dependencies\n"
    "✅ Backward-compatible (no public API changes)\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "⚠️ PAT scope blocker: The bot's GitHub PAT can create branches and push "
    "to forks but cannot open cross-org PRs via API (HTTP 403).\n"
    "\n"
    f"👉 One-click submission link:\n{compare_url}\n"
    "\n"
    "_(GitHub will pre-fill the title + body from the commit message. "
    'Just click "Create pull request".)_\n'
    "━━━━━━━━━━━━━━━━━━\n"
    "_Once submitted, the PR will be tracked in state.json and monitored "
    "every 30 min for maintainer review._\n"
    "_Tap the buttons below to control the bot._"
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
print(f"Compare URL: {compare_url}")
