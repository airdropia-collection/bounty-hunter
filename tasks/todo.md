# Bounty Hunter — Task Checklist

> Atomic tasks from `tasks/plan.md`. Each task is sized S or M per `skills/planning-and-task-breakdown/SKILL.md`.
> Mark `[x]` when done. Checkpoints require human review before proceeding.

## Phase 1: Foundation

- [ ] **Task 1: Project scaffolding**
  - Acceptance: pyproject.toml, requirements.txt, .gitignore, .env.example, LICENSE, README.md exist
  - Verify: `pip install -e ".[dev]"` succeeds; `ruff check .` passes
  - Files: `pyproject.toml`, `requirements.txt`, `.gitignore`, `.env.example`, `LICENSE`, `README.md`
  - Scope: S

- [ ] **Task 2: Core utilities (port from microwork-hunter)**
  - Acceptance: logger, sanitizer, state, retry modules work; 20+ tests pass
  - Verify: `pytest tests/test_utils/ -v` all green
  - Files: `src/utils/logger.py`, `src/utils/sanitizer.py`, `src/utils/state.py`, `src/utils/retry.py`, `tests/test_utils/*.py`
  - Scope: M

- [ ] **Task 3: Config module + health check**
  - Acceptance: `python -m src.health` prints config status; missing secrets flagged
  - Verify: Run health check locally with empty env — should warn, not crash
  - Files: `src/config.py`, `src/health.py`, `tests/test_config.py`
  - Scope: S

- [ ] **Task 4: GitHub client wrapper**
  - Acceptance: Can create/close/comment on Issues via API
  - Verify: `pytest tests/test_utils/test_github_client.py` passes with mocked API
  - Files: `src/utils/github_client.py`, `tests/test_utils/test_github_client.py`
  - Scope: M

### Checkpoint: Foundation
- [ ] All tests pass
- [ ] `python -m src.health` runs
- [ ] CI workflow green on GitHub Actions
- [ ] Human review before proceeding to Phase 2

---

## Phase 2: Scrapers

- [ ] **Task 5: BaseScraper + Bounty dataclass**
  - Acceptance: BaseScraper abstract class + Bounty dataclass with all fields from SPEC
  - Verify: `pytest tests/test_scrapers/test_base.py` passes
  - Files: `src/scrapers/base.py`, `tests/test_scrapers/test_base.py`
  - Scope: S

- [ ] **Task 6: Immunefi scraper**
  - Acceptance: Scrapes ≥10 bounties from immunefi.com with payout, severity, source URLs
  - Verify: `pytest tests/test_scrapers/test_immunefi.py` passes with fixture HTML
  - Files: `src/scrapers/immunefi.py`, `tests/test_scrapers/test_immunefi.py`, `tests/fixtures/immunefi/`
  - Scope: M

- [ ] **Task 7: Code4rana scraper**
  - Acceptance: Scrapes active contests with repo URL + scope
  - Verify: `pytest tests/test_scrapers/test_code4rena.py` passes
  - Files: `src/scrapers/code4rena.py`, `tests/test_scrapers/test_code4rena.py`, `tests/fixtures/code4rena/`
  - Scope: M

- [ ] **Task 8: Sherlock scraper**
  - Acceptance: Scrapes active Sherlock contests
  - Verify: `pytest tests/test_scrapers/test_sherlock.py` passes
  - Files: `src/scrapers/sherlock.py`, `tests/test_scrapers/test_sherlock.py`
  - Scope: M

- [ ] **Task 9: Gitcoin scraper (lower priority)**
  - Acceptance: Scrapes open Gitcoin bounties
  - Verify: `pytest tests/test_scrapers/test_gitcoin.py` passes
  - Files: `src/scrapers/gitcoin.py`, `tests/test_scrapers/test_gitcoin.py`
  - Scope: M

- [ ] **Task 10: Scraper integration tests**
  - Acceptance: All scrapers run in CI without crashing; dedup state works
  - Verify: `pytest tests/test_scrapers/ -v --integration` passes
  - Files: `tests/test_scrapers/test_integration.py`
  - Scope: S

### Checkpoint: Scrapers
- [ ] All 4 scrapers return ≥5 bounties each on real run
- [ ] Dedup state works (re-running doesn't re-add same bounties)
- [ ] HTML fixtures committed for reproducible tests
- [ ] Human review before proceeding to Phase 3

---

## Phase 3: AI Analysis

- [ ] **Task 11: AI helper (port from microwork-hunter)**
  - Acceptance: Gemini → Groq fallback works; lazy imports; sanitizer on errors
  - Verify: `pytest tests/test_analyzers/test_ai_helper.py` passes with mocked APIs
  - Files: `src/analyzers/ai_helper.py`, `tests/test_analyzers/test_ai_helper.py`
  - Scope: M

- [ ] **Task 12: Contract downloader**
  - Acceptance: Fetches Solidity source from GitHub URLs and Etherscan
  - Verify: `pytest tests/test_analyzers/test_contract_downloader.py` passes with mocked HTTP
  - Files: `src/analyzers/contract_downloader.py`, `tests/test_analyzers/test_contract_downloader.py`
  - Scope: M

- [ ] **Task 13: Slither integration**
  - Acceptance: Runs Slither on a sample contract, parses JSON output
  - Verify: `pytest tests/test_analyzers/test_slither.py` passes
  - Files: `src/analyzers/slither_runner.py`, `tests/test_analyzers/test_slither.py`
  - Scope: M

- [ ] **Task 14: AI vulnerability detector**
  - Acceptance: AI prompt template audits Solidity code, returns structured findings
  - Verify: `pytest tests/test_analyzers/test_vuln_detector.py` passes with mocked AI
  - Files: `src/analyzers/vuln_detector.py`, `tests/test_analyzers/test_vuln_detector.py`
  - Scope: M

- [ ] **Task 15: Severity classifier**
  - Acceptance: Maps findings to platform-specific severity levels (Immunefi/Code4rana/Sherlock)
  - Verify: `pytest tests/test_analyzers/test_severity_classifier.py` passes
  - Files: `src/analyzers/severity_classifier.py`, `tests/test_analyzers/test_severity_classifier.py`
  - Scope: S

- [ ] **Task 16: Doubt-driven review**
  - Acceptance: Second AI pass challenges findings using doubt-driven-development skill
  - Verify: `pytest tests/test_analyzers/test_doubt_review.py` passes
  - Files: `src/analyzers/doubt_review.py`, `tests/test_analyzers/test_doubt_review.py`
  - Scope: M

### Checkpoint: AI Analysis
- [ ] At least 1 finding per analyzed bounty (real or false-positive)
- [ ] Findings saved to `state/findings.json`
- [ ] AI token usage within free tier
- [ ] Human review before proceeding to Phase 4

---

## Phase 4: Reporting

- [ ] **Task 17: Report drafter**
  - Acceptance: AI-drafted markdown report per platform template (Immunefi/Code4rana/Sherlock)
  - Verify: `pytest tests/test_reporters/test_drafter.py` passes
  - Files: `src/reporters/drafter.py`, `src/reporters/templates/*.md.j2`, `tests/test_reporters/test_drafter.py`
  - Scope: M

- [ ] **Task 18: PoC generator**
  - Acceptance: AI-assembled Foundry test case for High/Critical findings
  - Verify: `pytest tests/test_reporters/test_poc_generator.py` passes
  - Files: `src/reporters/poc_generator.py`, `tests/test_reporters/test_poc_generator.py`
  - Scope: M

- [ ] **Task 19: GitHub Issue creator**
  - Acceptance: Creates formatted Issue with finding + report + PoC
  - Verify: `pytest tests/test_reporters/test_issue_creator.py` passes with mocked GitHub API
  - Files: `src/reporters/issue_creator.py`, `tests/test_reporters/test_issue_creator.py`
  - Scope: S

- [ ] **Task 20: Review-bot workflow**
  - Acceptance: Responds to `/submit <finding-id>` and `/reject <finding-id> <reason>` comments
  - Verify: Manual test on a real Issue
  - Files: `.github/workflows/review-bot.yml`, `src/reporters/review_handler.py`
  - Scope: M

### Checkpoint: Reporting
- [ ] End-to-end: scrape → analyze → draft → GitHub Issue created
- [ ] Review-bot responds to `/submit` and `/reject`
- [ ] Human review before proceeding to Phase 5

---

## Phase 5: Tracking + Polish

- [ ] **Task 21: Submission tracker**
  - Acceptance: Tracks submitted reports; polls status (submitted/accepted/paid/rejected)
  - Verify: `pytest tests/test_trackers/test_status.py` passes
  - Files: `src/trackers/status.py`, `tests/test_trackers/test_status.py`
  - Scope: M

- [ ] **Task 22: Earnings tracker**
  - Acceptance: Lifetime earnings by platform; weekly/monthly summaries
  - Verify: `pytest tests/test_trackers/test_earnings.py` passes
  - Files: `src/trackers/earnings.py`, `tests/test_trackers/test_earnings.py`
  - Scope: S

- [ ] **Task 23: Daily hunt workflow**
  - Acceptance: GitHub Actions runs every 6 hours; full pipeline completes in <30 min
  - Verify: Manual trigger via workflow_dispatch succeeds
  - Files: `.github/workflows/hunt.yml`, `src/pipeline.py`
  - Scope: M

- [ ] **Task 24: Documentation**
  - Acceptance: README, ROADMAP, CONTRIBUTING, SECURITY, CHANGELOG all exist
  - Verify: All markdown renders correctly on GitHub
  - Files: `README.md`, `docs/ROADMAP.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`
  - Scope: M

- [ ] **Task 25: Knowledge base structure**
  - Acceptance: `docs/vuln-patterns/` has templates for top 10 SWC registry entries
  - Verify: `ls docs/vuln-patterns/` shows 10+ markdown files
  - Files: `docs/vuln-patterns/*.md`
  - Scope: S

### Checkpoint: Complete
- [ ] Pipeline runs unattended for 24 hours
- [ ] First GitHub Issue created with real finding
- [ ] All tests pass, CI green
- [ ] Ready for first manual submission

---

**Total tasks:** 25
**Estimated time:** 21 days (1-2 hours/day)
**First milestone:** First $1 earned (~30 days from start)
