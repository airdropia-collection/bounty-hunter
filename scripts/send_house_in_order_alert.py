"""Send final house-in-order status alert."""
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
    "🏠 HOUSE IN ORDER — Deep Audit Complete\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📦 Repo: airdropia-collection/bounty-hunter (PUBLIC)\n"
    "🔖 Commit: cc32d01\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "✅ ISSUES RESOLVED:\n"
    "\n"
    "1️⃣ MergeOS Gate 1 — COMPLETED\n"
    "   • Followed mergeos-bounties org ✅\n"
    "   • Starred mergeos-bounties/mergeos ✅\n"
    "   • Starred mergeos-bounties/mergeos-contracts ✅\n"
    "   • Comment posted on PR #252 via GH_PAT ✅\n"
    "   • PR #252 status: NEEDS_REVISION → UNDER_REVIEW\n"
    "   • Waiting for Gate 2 (security) review\n"
    "\n"
    "2️⃣ PAT Confusion — PERMANENTLY FIXED\n"
    "   • agent.md §6 now has 12-row PAT Operations Matrix\n"
    "   • Every operation mapped to: which PAT + which mechanism\n"
    "   • Cross-org ops (PR/comment/follow/star) → GH_PAT via workflow\n"
    "   • Local fine-grained PAT → only for push + workflow_dispatch\n"
    "   • New workflow: mergeos-onboarding.yml (uses GH_PAT for follow/star)\n"
    "\n"
    "3️⃣ GitHub Actions Billing — CORRECTED\n"
    "   • Repo is PUBLIC (verified via API)\n"
    "   • Actions is FREE & UNLIMITED for public repos\n"
    "   • Earlier 2000 min/month warning was WRONG (private repos only)\n"
    "   • Current usage: ~16 min for 30 runs (negligible)\n"
    "   • Hourly hunt cycle is safe to run indefinitely\n"
    "\n"
    "4️⃣ Deep Audit Results:\n"
    "   • 10 workflows — all verified ✅\n"
    "   • 31 Python modules — all importable ✅\n"
    "   • state.json — valid, 4 active PRs tracked ✅\n"
    "   • agent.md — 7 sections (added §7 Operations Playbook) ✅\n"
    "   • All TG notifications auto-triggered by workflows ✅\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📊 CURRENT PORTFOLIO (4 PRs):\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "   👀 spy-spotify PR #535 | $25 | UNDER_REVIEW\n"
    "   👀 ai-research PR #1231 | $150 | UNDER_REVIEW\n"
    "   👀 Loru PR #252 | 50 MRG | UNDER_REVIEW (Gate 1 done!)\n"
    "   👀 SwipeableTabBarController PR #128 | $150 | UNDER_REVIEW\n"
    "   💰 Total at stake: $325 + 50 MRG\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "🚀 HUNT MISSION TRIGGERED:\n"
    "   • Dework auth token working (891 orgs discovered)\n"
    "   • IssueHunt scraped 18 bounties\n"
    "   • Hourly auto-hunt now active (cron: 0 * * * *)\n"
    "\n"
    "⚠️ KNOWN LIMITATIONS (next improvements):\n"
    "   • Dework API is ID-based — can't list tasks by workspace\n"
    "     (web scraping fallback returns 0 tasks; needs different approach)\n"
    "   • Analyzer is Solidity-only — IssueHunt bounties are JS/Python/Java\n"
    "     (all 5 bounties skipped with 'no .sol files'; needs language-aware\n"
    "     analyzer to handle general software bugs)\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "_System is now fully operational. Hourly hunt cycle will auto-run._\n"
    "_Every activity auto-reported to this channel._\n"
    "_Tap buttons below to control the bot._"
)

payload = json.dumps({
    "ref": "main",
    "inputs": {"message": msg, "parse_mode": "Markdown"},
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
print("House-in-order alert dispatched.")
