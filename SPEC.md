# Spec: Bounty Hunter

## Objective

Build an AI-powered bug bounty hunting system that:

1. **Scrapes** active bounties from Web3 platforms (Immunefi, Code4rana, Sherlock, Gitcoin)
2. **Filters** bounties by feasibility — AI estimates difficulty and potential payout for each
3. **Analyzes** smart contract source code with AI (Gemini → Groq fallback) to find vulnerabilities
4. **Drafts** vulnerability reports with severity, impact, PoC, and remediation
5. **Creates GitHub Issues** for each promising finding → human (you) reviews and approves
6. **Tracks** submission status across platforms (submitted, accepted, paid, rejected)
7. **Learns** from past findings — accumulates a knowledge base of vulnerability patterns

The user's role is reduced to: review the GitHub Issue → approve or reject → AI submits the approved reports.

## Tech Stack

- **Language:** Python 3.11+ (same as microwork-hunter, proven stack)
- **Browser automation:** patchright (Cloudflare bypass) — only if needed for scraping
- **HTTP scraping:** httpx + selectolax (fast HTML parsing)
- **AI:** google-generativeai (Gemini 1.5-flash, 1M tok/day free) + openai client pointed at Groq (Llama-3.1-70B, 1M tok/day free)
- **Web3 specific:** slither-analyzer (Solidity static analysis), web3.py (RPC calls)
- **State:** JSON files (no DB — keep $0 budget, version-controlled)
- **CI/CD:** GitHub Actions free tier (2000 min/month)
- **Testing:** pytest + pytest-asyncio
- **Linting:** ruff
- **Skills layer:** addyosmani/agent-skills (all 24 skills vendored in `skills/`)

## Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

# Lint
ruff check src tests

# Tests
pytest -v
pytest --cov=src --cov-report=term-missing

# Local dev runs
python -m src.scrapers.immunefi           # Scrape Immunefi bounties
python -m src.scrapers.code4rena          # Scrape Code4rana contests
python -m src.analyzers.pipeline          # Run AI analysis on pending bounties
python -m src.reporters.drafter           # Draft reports for high-priority findings
python -m src.trackers.status             # Check submission statuses
python -m src.health                      # Health check (like microwork-hunter)

# Full pipeline (used by GitHub Actions)
python -m src.pipeline                    # scrape → filter → analyze → draft → issue
```

## Project Structure

```
bounty-hunter/
├── AGENTS.md                         # AI agent operating rules (from agent-skills)
├── README.md
├── SPEC.md                           # This file
├── CHANGELOG.md
├── SECURITY.md
├── CONTRIBUTING.md
├── LICENSE                           # MIT
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
│
├── .github/
│   ├── workflows/
│   │   ├── hunt.yml                  # Daily scrape + analyze pipeline
│   │   ├── review-bot.yml            # Responds to /submit /reject comments
│   │   └── ci.yml                    # Lint + tests on every PR
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.yml
│   │   ├── feature_request.yml
│   │   └── new_platform.yml
│   ├── CODEOWNERS
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── dependabot.yml
│
├── skills/                           # 24 agent-skills (vendored from addyosmani/agent-skills)
│   ├── spec-driven-development/
│   ├── planning-and-task-breakdown/
│   ├── security-and-hardening/       # ← most important for bounty hunter
│   ├── doubt-driven-development/     # ← critical for high-stakes submissions
│   ├── source-driven-development/
│   ├── incremental-implementation/
│   ├── test-driven-development/
│   ├── code-review-and-quality/
│   ├── debugging-and-error-recovery/
│   ├── ... (all 24)
│
├── agents/                           # 4 specialist personas
│   ├── code-reviewer.md
│   ├── security-auditor.md           # ← primary persona for bounty work
│   ├── test-engineer.md
│   └── web-performance-auditor.md
│
├── references/                       # 7 checklists
│   ├── security-checklist.md
│   ├── definition-of-done.md
│   ├── testing-patterns.md
│   ├── observability-checklist.md
│   ├── orchestration-patterns.md
│   ├── performance-checklist.md
│   └── accessibility-checklist.md
│
├── docs/
│   ├── ROADMAP.md                    # Day1/Week1/Month1/Year1 targets
│   ├── architecture.md               # System diagram + data flow
│   ├── vuln-patterns/                # Knowledge base of discovered patterns
│   │   ├── reentrancy.md
│   │   ├── access-control.md
│   │   ├── oracle-manipulation.md
│   │   └── ...
│   └── platforms/                    # Per-platform notes
│       ├── immunefi.md
│       ├── code4rena.md
│       └── sherlock.md
│
├── src/
│   ├── __init__.py
│   ├── config.py                     # Reads env vars / GitHub Secrets
│   ├── pipeline.py                   # Orchestrator: scrape → filter → analyze → draft
│   ├── health.py                     # Startup health check CLI
│   │
│   ├── scrapers/                     # Per-platform bounty scrapers
│   │   ├── __init__.py
│   │   ├── base.py                   # BaseScraper + Bounty dataclass
│   │   ├── immunefi.py               # Immunefi bug bounty listings
│   │   ├── code4rena.py              # Code4rana audit contests
│   │   ├── sherlock.py               # Sherlock audit contests
│   │   └── gitcoin.py                # Gitcoin open-source bounties
│   │
│   ├── analyzers/                    # AI-powered analysis
│   │   ├── __init__.py
│   │   ├── ai_helper.py              # Gemini → Groq fallback (port from microwork)
│   │   ├── contract_analyzer.py      # Solidity source code analysis
│   │   ├── vuln_detector.py          # Pattern-based vuln detection
│   │   └── severity_classifier.py    # CVSS-style severity scoring
│   │
│   ├── reporters/                    # Report drafting
│   │   ├── __init__.py
│   │   ├── drafter.py                # AI-drafted vulnerability reports
│   │   ├── poc_generator.py          # Proof-of-concept code generation
│   │   └── templates/                # Per-platform report templates
│   │       ├── immunefi.md.j2
│   │       ├── code4rena.md.j2
│   │       └── sherlock.md.j2
│   │
│   ├── trackers/                     # Submission tracking
│   │   ├── __init__.py
│   │   ├── status.py                 # Check submission statuses
│   │   └── earnings.py               # Track payouts (like microwork earnings_tracker)
│   │
│   └── utils/                        # Cross-cutting concerns
│       ├── __init__.py
│       ├── logger.py                 # Centralized logging (port from microwork)
│       ├── sanitizer.py              # Secret sanitizer (port from microwork)
│       ├── state.py                  # Task dedup + bounty state (port from microwork)
│       ├── retry.py                  # Tenacity-based retries (port from microwork)
│       ├── github_client.py          # GitHub Issues + PRs API wrapper
│       └── web3/                     # Web3-specific helpers
│           ├── abi_loader.py
│           ├── rpc.py                # Multi-chain RPC (free endpoints)
│           └── chain_ids.py
│
├── tests/
│   ├── conftest.py
│   ├── test_scrapers/
│   │   ├── test_immunefi.py
│   │   └── test_code4rena.py
│   ├── test_analyzers/
│   │   ├── test_ai_helper.py
│   │   └── test_vuln_detector.py
│   ├── test_reporters/
│   │   └── test_drafter.py
│   └── test_utils/
│       ├── test_state.py
│       └── test_sanitizer.py
│
├── tasks/                            # Planning artifacts (from spec-driven-development skill)
│   ├── plan.md                       # High-level implementation plan
│   └── todo.md                       # Atomic task checklist
│
├── state/                            # Runtime state (gitignored)
│   ├── bounties_seen.json            # Dedup — don't re-analyze seen bounties
│   ├── findings.json                 # AI-discovered findings awaiting review
│   ├── submissions.json              # Submitted reports + status
│   └── earnings.json                 # Lifetime earnings tracker
│
└── cache/                            # Scraped HTML / contract source (gitignored)
    ├── immunefi/
    ├── code4rena/
    └── contracts/
```

## Code Style

Follow `skills/spec-driven-development/` + `skills/code-review-and-quality/` conventions.

**Python style:**
- `from __future__ import annotations` at top of every file
- Type hints mandatory on all public functions
- `log = get_logger("module.name")` — never `print()`
- Dataclasses for all data structures (not dicts)
- Async where I/O-bound (httpx.AsyncClient, playwright.async_api)
- Sync where CPU-bound (AI calls in CI, no benefit from async)

**Example:**
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from src.utils.logger import get_logger

log = get_logger("scrapers.immunefi")


@dataclass
class Bounty:
    """A scraped bounty listing."""
    id: str                          # platform-native ID
    platform: str                    # "immunefi" | "code4rana" | ...
    project_name: str
    description: str
    max_payout_usd: int              # highest tier
    severity_levels: list[str]       # ["critical", "high", ...]
    tech_stack: list[str]            # ["solidity", "foundry", ...]
    source_urls: list[str]           # GitHub repos / contract addresses
    deadline: Optional[str] = None
    url: str = ""
    tags: list[str] = field(default_factory=list)
```

## Testing Strategy

**Frameworks:** pytest + pytest-asyncio + pytest-cov + respx (HTTP mocking)

**Coverage targets:**
- `src/utils/` — 90%+ (pure logic, easy to test)
- `src/scrapers/` — 70%+ (HTTP mocking with respx)
- `src/analyzers/` — 60%+ (AI calls mocked, prompt logic tested)
- `src/reporters/` — 60%+ (template rendering tested)

**Test pyramid (per `skills/test-driven-development/`):**
- 80% unit tests — pure functions, mocked I/O
- 15% integration tests — real scraper runs against cached HTML
- 5% E2E tests — full pipeline run with mock AI

**Beyonce Rule:** "If you care about it, test it." Untested code is broken code.

**Locations:**
- `tests/test_<module>.py` mirrors `src/<module>.py`
- `tests/fixtures/` for cached HTML, sample contracts, sample reports

## Boundaries

### Always do:
- Run `pytest` before every commit
- Run `ruff check` before every commit
- Validate all external input (scraped HTML, AI output) at system boundaries
- Treat all AI output as untrusted — never submit without human review
- Save all state to `state/` (gitignored) — never commit runtime state
- Log with structured logging (JSON mode in CI)
- Use `skills/security-and-hardening/` checklist for all security-sensitive code

### Ask first:
- Adding new bounty platform scrapers (requires API TOS review)
- Changing AI prompt templates (affects report quality)
- Submitting reports automatically without human `/approve`
- Adding new external dependencies (supply-chain risk per `skills/security-and-hardening/`)
- Modifying GitHub Actions workflows

### Never do:
- Submit reports without explicit human `/approve` comment
- Commit API keys, wallet private keys, or session cookies
- Use AI-generated PoCs without local testing first
- Skip the `doubt-driven-development` review for high-severity findings
- Auto-merge PRs without code review
- Store wallet private keys in any file (even gitignored)

## Success Criteria

**Phase 1 (Week 1-2): Pipeline works end-to-end**
- [ ] Daily GitHub Actions run completes without errors
- [ ] Scrapes ≥10 bounties from Immunefi/Code4rana
- [ ] AI analyzes ≥3 bounties per run
- [ ] At least 1 GitHub Issue created per run with finding summary

**Phase 2 (Month 1): First submission**
- [ ] At least 1 vulnerability report submitted to a platform
- [ ] Submission tracked in `state/submissions.json`
- [ ] Earnings tracker shows actual payout (even $1 counts)

**Phase 3 (Month 3): Sustainable cadence**
- [ ] 3-5 submissions per month
- [ ] Knowledge base (`docs/vuln-patterns/`) has 10+ patterns
- [ ] At least 1 paid bounty ($100+)
- [ ] Pipeline runs unattended for 7+ days without intervention

**Phase 4 (Year 1): Real income**
- [ ] $1,000+ total earnings
- [ ] Reputation on at least 1 platform (top 100 on Immunefi or Code4rana leaderboard)
- [ ] Portfolio of 20+ submitted reports

## Open Questions

1. **Wallet setup:** Some platforms (Gitcoin) require a wallet for payouts. Should we use the user's existing wallet or create a dedicated one? **Default: user provides wallet address via secret `WALLET_ADDRESS` (no private key ever stored).**

2. **AI model selection:** Gemini 1.5-flash is fast but may miss subtle vulns. Groq's Llama-3.1-70B is more thorough but slower. **Default: run both, use doubt-driven-development skill to reconcile disagreements.**

3. **PoC testing:** AI-generated PoCs need local execution to verify. Should we spin up a local Hardhat/Foundry fork in CI? **Default: yes, but only for High/Critical findings. Low/Medium = AI-assembled PoC + human verification note.**

4. **Disclosure timing:** Some platforms require embargo periods. **Default: never auto-disclose. All submissions go through platform's native submission flow, which handles disclosure.**

5. **Multi-account:** Should we run bounties across multiple accounts? **Default: NO. Single account builds reputation. Multi-account is TOS violation on most platforms.**

---

**Spec version:** 1.0
**Created:** 2026-07-15
**Skill used:** `skills/spec-driven-development/SKILL.md`
**Next step:** `skills/planning-and-task-breakdown/SKILL.md` → `tasks/plan.md` + `tasks/todo.md`
