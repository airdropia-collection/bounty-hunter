# 🎯 Bounty Hunter — Roadmap & Targets

> Updated 2026-07-19 (Cycle 11): Aligned with current polyglot self-healing architecture.

## Current Operational Reality

The bot operates as a **value-agnostic, polyglot, self-healing agent swarm** that targets bounties backed by **real fiat or on-chain crypto** (verified via 5-point Pre-Flight Reconnaissance Protocol). Virtual credits, reputation points, and un-deployed tokens are automatically rejected.

## Verified Platforms

| Platform | Asset Type | Escrow | Status | Avg Bounty |
|----------|-----------|--------|--------|------------|
| **Opire** (claude-builders-bounty) | USD via Stripe | Opire holds funds | ✅ REAL-ASSET-VERIFIED | $50-$200 |
| **IssueHunt** | USD via Stripe Connect | IssueHunt holds funds | ✅ REAL-ASSET-VERIFIED | $20-$150 |
| **Dework** | Crypto (USDC/ETH) | TBD | ⏸️ UNVERIFIED (held) | $200-$2500 |
| **MergeOS** | MRG (internal credit) | Internal database | ❌ VIRTUAL-CREDIT-FLAGGED | $0 withdrawable |

## Active Earnings Pipeline

| Status | Count | Value |
|--------|-------|-------|
| MERGED (secured) | 6 PRs | 150 MRG ($0 withdrawable) |
| PR_SUBMITTED (CBB) | 3 PRs | $300 USD (real Stripe escrow) |
| UNDER_REVIEW (IssueHunt) | 3 PRs | $325 USD (real Stripe escrow) |
| **Total real USD pending** | **6 PRs** | **$625 USD** |

## Architecture Stack

- **Languages:** Python (95%), TypeScript (82%), Go (80%), Rust (78%), Bash (90%), Dockerfile (85%), YAML (92%), Markdown (95%), JSON (98%)
- **Test Harness:** pytest, go test, cargo test, npm test, shellcheck
- **Self-Healing:** 3-iteration loop with 10 error pattern matchers
- **Memory:** Atomic write to docs/agent_memory.json (auto-persist on heal)
- **Telemetry:** Dual-engine Telegram (Pinned HUD + Lifecycle Cards)
- **Verification:** 4-layer gate (Pre-Flight → Asset Gate → Gate Alpha → Gate Beta)

## Removed Components (Cycle 11 Purge)

- `src/analyzers/vuln_detector.py` — AI vuln detection (0% ROI, token-burning)
- `src/analyzers/ai_helper.py` — Gemini/Groq LLM client (token-burning)
- `src/analyzers/doubt_review.py` — Adversarial review (depended on vuln_detector)
- `src/reporters/drafter.py` — AI report drafter (unused)
- `src/reporters/poc_generator.py` — Foundry PoC generator (unused)
- `src/trackers/` — Empty directory
- `scripts/swift_fix/` — One-off Swift fix files
- `scripts/send_*_alert.py` — One-off alert scripts (5 files)

## Future Milestones

1. **First real USD payout** — When PR #3498, #3499, or #3500 merges on CBB
2. **Dework verification** — Complete 5-point Pre-Flight check for Dework platform
3. **Go/Rust bounty execution** — First polyglot target outside Python
4. **Automated Opire scraper** — Dedicated scraper for Opire-labeled GitHub issues
5. **Platform re-verification cron** — 30-day automated re-check of all platforms
