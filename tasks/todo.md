# Bounty Hunter — Task Checklist

> Updated 2026-07-19 (Cycle 11): Reflects current operational reality.
> Legacy platform tasks (Immunefi/Code4rena/Sherlock) removed — those
> scrapers are in LEGACY_SCRAPER_MAP and not used by default.

## Phase 1: Foundation ✅ COMPLETE
- [x] Project scaffolding (pyproject.toml, requirements.txt, etc.)
- [x] Core utilities (logger, sanitizer, state, retry)
- [x] Config module + health check
- [x] GitHub client wrapper

## Phase 2: Scrapers ✅ COMPLETE
- [x] BaseScraper + Bounty dataclass
- [x] IssueHunt scraper (JSON parser, githubState filter, verify_open_on_github)
- [x] Dework scraper (KYC filter, non-code-task filter) — UNVERIFIED status
- [x] Legacy scrapers (immunefi, code4rena, sherlock) — kept for manual use

## Phase 3: AI Analysis ❌ REMOVED (0% ROI)
- [x] ~~AI helper (Gemini → Groq fallback)~~ — DELETED Cycle 11
- [x] ~~Contract downloader~~ — KEPT (used by GitHub Search fallback)
- [x] ~~AI vulnerability detector~~ — DELETED Cycle 11
- [x] ~~Doubt-driven review~~ — DELETED Cycle 11

## Phase 4: Reporting — PARTIALLY COMPLETE
- [x] ~~Report drafter~~ — DELETED Cycle 11
- [x] ~~PoC generator~~ — DELETED Cycle 11
- [x] Review-bot workflow (/submit, /reject commands)
- [x] Direct solution construction (solutions/ directory)

## Phase 5: Architecture Upgrades ✅ COMPLETE
- [x] Pre-Flight Reconnaissance Protocol (agent.md §0, 5-point gate)
- [x] Hard Fiat/Crypto Gate (config.py, accepted/rejected asset types)
- [x] Capability Matrix (10 languages, 80% confidence threshold)
- [x] Polyglot Test Runner (pytest, go test, cargo test, npm test)
- [x] Batch Executor (value-agnostic, 3-iteration self-healing)
- [x] Memory Registry (atomic write, auto-persist learned patterns)
- [x] Dual-Engine Telemetry (Pinned HUD + Lifecycle Cards)
- [x] Cold Storage Archive (docs/archive_ledger.json)
- [x] Agent Memory Registry (docs/agent_memory.json)
- [x] Live Batch Workflow (hunt-batch.yml, every 6h)

## Phase 6: Active Targets (Real USD)
- [ ] PR #3498 (CBB #3, $100) — awaiting merge
- [ ] PR #3499 (CBB #1, $50) — awaiting merge
- [ ] PR #3500 (CBB #4, $150) — awaiting merge
- [ ] PR #535 (IssueHunt, $25) — awaiting review
- [ ] PR #1231 (IssueHunt, $150) — awaiting review
- [ ] PR #128 (IssueHunt, $150) — awaiting review

## Phase 7: Backlog
- [ ] Dework platform verification (5-point Pre-Flight check)
- [ ] Automated Opire bounty scraper
- [ ] Platform re-verification cron (30-day cadence)
- [ ] CBB fork cleanup integration (fork-cleanup.yml)
- [ ] Stale MergeOS branch cleanup (7 branches on origin, virtual credit)
