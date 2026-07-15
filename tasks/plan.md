# Implementation Plan: Bounty Hunter

## Overview

Build an AI-powered Web3 bug bounty hunting system that scrapes bounties from Immunefi/Code4rana/Sherlock, analyzes smart contracts with Gemini/Groq, drafts vulnerability reports, and tracks submissions. Runs on GitHub Actions free tier with $0 budget.

## Architecture Decisions

### 1. Python 3.11+ (not TypeScript)
**Rationale:** Same stack as microwork-hunter (proven). Better AI/ML ecosystem (google-generativeai, slither-analyzer). Simpler deployment (no build step).

### 2. JSON file state (not SQLite/Postgres)
**Rationale:** $0 budget. Version-controllable. No DB to manage. File sizes will be small (bounties_seen ~1MB after a year). Use `src/utils/state.py` pattern from microwork-hunter.

### 3. Sync AI calls in CI, async scrapers
**Rationale:** Scrapers are I/O-bound (HTTP) → async httpx. AI calls are sequential per-bounty → sync is simpler. Avoids "sync API on sync scheduler" bug we hit in microwork-hunter.

### 4. Human-in-the-loop via GitHub Issues
**Rationale:** Same proven pattern as microwork-hunter. `/submit` and `/reject` commands. No external notification system needed.

### 5. Vendor agent-skills (not npm install)
**Rationale:** Skills are markdown files. Vendoring = no runtime dependency, no supply-chain risk, can customize per project. 24 skills + 4 agents + 7 references = ~150KB total.

### 6. patchright for scraping (not raw requests)
**Rationale:** Immunefi uses Cloudflare. microwork-hunter proved patchright works. Fallback to httpx for sites that don't need JS.

### 7. Slither + AI (not AI alone)
**Rationale:** Slither catches known patterns deterministically (reentrancy, uninitialized storage). AI catches novel patterns + writes reports. Combination > either alone.

## Task List

### Phase 1: Foundation (Days 1-3)

- [ ] Task 1: Project scaffolding — pyproject.toml, requirements.txt, .gitignore, .env.example, LICENSE
- [ ] Task 2: Core utilities — logger, sanitizer, state, retry (port from microwork-hunter)
- [ ] Task 3: Config module — read env vars, validate secrets, health check CLI
- [ ] Task 4: GitHub client wrapper — Issues create/comment/close, PR create

**Checkpoint: Foundation**
- [ ] `pytest` passes (with stub tests)
- [ ] `python -m src.health` runs and reports config status
- [ ] CI workflow (lint + test) passes on GitHub Actions

### Phase 2: Scrapers (Days 4-7)

- [ ] Task 5: BaseScraper + Bounty dataclass
- [ ] Task 6: Immunefi scraper — list bounties, parse payout tiers, extract source URLs
- [ ] Task 7: Code4rana scraper — list active contests, extract repo + scope
- [ ] Task 8: Sherlock scraper — list active contests
- [ ] Task 9: Gitcoin scraper — list open bounties (lower priority, easier entry)
- [ ] Task 10: Scraper tests with cached HTML fixtures

**Checkpoint: Scrapers**
- [ ] All 4 scrapers return ≥5 bounties each on real run
- [ ] Dedup state works (re-running doesn't re-add same bounties)
- [ ] HTML fixtures committed for reproducible tests

### Phase 3: AI Analysis (Days 8-12)

- [ ] Task 11: AI helper — Gemini → Groq fallback (port from microwork-hunter)
- [ ] Task 12: Contract downloader — fetch Solidity source from GitHub/Etherscan
- [ ] Task 13: Slither integration — run static analysis, parse JSON output
- [ ] Task 14: AI vulnerability detector — prompt template for Solidity audit
- [ ] Task 15: Severity classifier — map findings to Immunefi/Code4rana severity levels
- [ ] Task 16: Doubt-driven review — run second AI pass to challenge findings

**Checkpoint: AI Analysis**
- [ ] At least 1 vulnerability finding per analyzed bounty (real or false-positive)
- [ ] Findings saved to `state/findings.json` with full evidence trail
- [ ] AI cost stays within free tier (track token usage)

### Phase 4: Reporting (Days 13-16)

- [ ] Task 17: Report drafter — AI-drafted markdown report per platform template
- [ ] Task 18: PoC generator — AI-assembled Foundry/Hardhat test case
- [ ] Task 19: GitHub Issue creator — formatted issue with finding + report + PoC
- [ ] Task 20: Review-bot workflow — `/submit <finding-id>` and `/reject <finding-id> <reason>`

**Checkpoint: Reporting**
- [ ] End-to-end: scrape → analyze → draft → GitHub Issue created
- [ ] Review-bot responds to `/submit` and `/reject` comments
- [ ] Issue template renders correctly on GitHub

### Phase 5: Tracking + Polish (Days 17-21)

- [ ] Task 21: Submission tracker — track submitted reports + status polling
- [ ] Task 22: Earnings tracker — lifetime earnings by platform
- [ ] Task 23: Daily hunt workflow — scheduled 6-hourly scrape + analyze
- [ ] Task 24: Documentation — README, ROADMAP, CONTRIBUTING, SECURITY
- [ ] Task 25: Knowledge base structure — `docs/vuln-patterns/` initial templates

**Checkpoint: Complete**
- [ ] Pipeline runs unattended for 24 hours
- [ ] First GitHub Issue created with real finding
- [ ] All tests pass, CI green
- [ ] Ready for first manual submission

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| AI hallucinates vulnerabilities (false positives) | High — wastes human review time, risks submitting invalid reports | Doubt-driven-development skill: second AI pass challenges findings. Human `/approve` mandatory. Track false-positive rate. |
| AI misses real vulnerabilities (false negatives) | Medium — lost bounty opportunities | Combine AI + Slither (deterministic). Run multiple AI models (Gemini + Groq). Track coverage over time. |
| Platform TOS violation (banned from Immunefi etc.) | High — loses reputation + future earnings | Read each platform's TOS before scraping. Use official APIs where available. Rate-limit scrapers (1 req/sec). |
| AI cost exceeds free tier | Medium — pipeline halts | Monitor token usage daily. Auto-pause if >80% of daily quota used. Cache AI responses (same contract = same analysis). |
| Contract source unavailable (private/verified-only) | Low — skip that bounty | Graceful degradation: if no source, AI analyzes from bytecode (less effective but possible). |
| GitHub Actions quota (2000 min/month) | Medium — pipeline can't run | Optimize scraper concurrency. Cache HTML. Cap daily runs at 4 (every 6 hours). |
| Wallet compromise (private key leak) | Critical — loss of funds | NEVER store private keys. Wallet address only (for receiving payouts). Use hardware wallet for withdrawals. |

## Open Questions

1. **Immunefi API:** Does Immunefi have an official API, or must we scrape HTML? (Need to check their TOS.)
2. **Code4rana contest format:** Are contest submissions anonymous? Does AI-assisted analysis violate contest rules?
3. **Slither installation:** Slither requires Solc. Can we install both in GitHub Actions within the 30-minute job limit?
4. **Multi-chain RPC:** Which free RPC endpoints are most reliable for mainnet forking? (Infura free tier? Alchemy free tier? Public endpoints?)

---

**Plan version:** 1.0
**Created:** 2026-07-15
**Skill used:** `skills/planning-and-task-breakdown/SKILL.md`
**Next step:** `tasks/todo.md` (atomic checklist) → then `skills/incremental-implementation/SKILL.md` for execution
