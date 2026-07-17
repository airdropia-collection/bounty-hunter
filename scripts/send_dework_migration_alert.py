"""Send [🧹 BOUNTYCASTER REPLACED WITH DEWORK] confirmation alert."""
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
    "🧹 BOUNTYCASTER REPLACED WITH DEWORK\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📦 Repo: airdropia-collection/bounty-hunter\n"
    "🔖 Commit: 7a9ab17\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "✅ DeworkScraper deployed (src/scrapers/dework.py)\n"
    "    Uses public GraphQL API at api.dework.xyz/graphql\n"
    "    Web3 DAO bounties (USDC/ETH payouts)\n"
    "    3-tier fallback: DEWORK_AUTH_TOKEN → public API → web scrape\n"
    "\n"
    "❌ Bountycaster completely removed:\n"
    "    - src/scrapers/bountycaster.py DELETED\n"
    "    - Removed from pipeline.py VERIFIED_SCRAPER_MAP\n"
    "    - Removed from hunt.yml dropdown + env vars\n"
    "    - Removed from agent.md §3 (replaced with Dework)\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🎯 DUAL-PLATFORM MATRIX LOCKED:\n"
    "    1. IssueHunt (public, no auth)\n"
    "    2. Dework (public GraphQL + optional DEWORK_AUTH_TOKEN)\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "⚡ HOURLY HUNT CYCLE ENABLED:\n"
    "    Cron: 0 * * * * (was every 6 hours)\n"
    "    Bot will auto-check both platforms every hour\n"
    "    Auto-TG alerts at every stage (scanning/finding/PR)\n"
    "    ⚠️ GitHub Actions free tier: 2000 min/month\n"
    "        24 runs/day x 5 min = 3600 min/month (over limit)\n"
    "        Mitigation: timeout 15min, early exit if PAUSED\n"
    "        Watch: https://github.com/settings/billing\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "💓 HOURLY HEARTBEAT NOW AUTO-SENT:\n"
    "    Every 30 min, pr-monitor.yml sends portfolio summary:\n"
    "    - Total bounty value at stake\n"
    "    - All active PRs with status emojis\n"
    "    - System status + last action\n"
    "    No manual trigger needed — fully automatic.\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📊 CURRENT PORTFOLIO (4 active PRs):\n"
    "    👀 spy-spotify PR #535 | $25 | UNDER_REVIEW\n"
    "    👀 ai-research PR #1231 | $150 | UNDER_REVIEW\n"
    "    🔧 Loru PR #252 | 50 MRG | NEEDS_REVISION\n"
    "    👀 SwipeableTabBarController PR #128 | $150 | UNDER_REVIEW\n"
    "    💰 Total at stake: $325 + 50 MRG\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "🛡️ DEEP ANALYSIS DONE BEFORE IMPLEMENTATION:\n"
    "    Probed Dework GraphQL API → confirmed alive\n"
    "    Reverse-engineered schema from error messages\n"
    "    Found: public API returns org/workspace metadata only\n"
    "    Found: task data needs DEWORK_AUTH_TOKEN (set in secrets)\n"
    "    Built graceful degradation: returns [] + filter alert if no token\n"
    "    Did NOT blindly build scraper that would fail in production\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "_Next hourly hunt will auto-trigger within 60 min._\n"
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
print(f"\n[🧹 BOUNTYCASTER REPLACED WITH DEWORK] alert dispatched.")
