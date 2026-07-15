# AGENTS.md

This file configures AI coding agents working on the bounty-hunter repository.

## Repository Overview

AI-powered Web3 bug bounty hunting system. Scrapes Immunefi/Code4rana/Sherlock, analyzes smart contracts with Gemini/Groq, drafts vulnerability reports, tracks submissions. Runs on GitHub Actions free tier. $0 budget.

**Primary spec:** `SPEC.md`
**Implementation plan:** `tasks/plan.md`
**Task checklist:** `tasks/todo.md`

## Skill-Driven Execution

This repo vendors all 24 skills from `addyosmani/agent-skills` in `skills/`.
Skills are the **mandatory workflows** for every task. Do not implement directly
if a skill applies — invoke the skill first.

### Core Rules (non-negotiable)

1. **If a task matches a skill, you MUST invoke it** — read `skills/<name>/SKILL.md` and follow its steps in order
2. **Skills are located at `skills/<skill-name>/SKILL.md`**
3. **Never implement directly if a skill applies** — even 1% match means invoke
4. **Always follow the skill workflow exactly** — do not partially apply
5. **Verification is non-negotiable** — every skill ends with evidence requirements

### Intent → Skill Mapping

| Intent | Skill |
|--------|-------|
| New feature / significant change | `spec-driven-development` → update `SPEC.md` first |
| Breaking down work | `planning-and-task-breakdown` → update `tasks/plan.md` + `tasks/todo.md` |
| Implementing code | `incremental-implementation` + `test-driven-development` |
| Writing tests | `test-driven-development` |
| Bug / unexpected behavior | `debugging-and-error-recovery` |
| Code review (before merge) | `code-review-and-quality` |
| Security-sensitive code | `security-and-hardening` (mandatory for scrapers, AI output handling, key management) |
| Simplifying complex code | `code-simplification` |
| High-stakes decision (e.g., submitting a report) | `doubt-driven-development` |
| Verifying framework facts | `source-driven-development` |
| Committing / branching | `git-workflow-and-versioning` |
| CI/CD pipeline changes | `ci-cd-and-automation` |
| Writing docs / ADRs | `documentation-and-adrs` |
| Deploying / launching | `shipping-and-launch` |

### Lifecycle Mapping

```
DEFINE  → spec-driven-development
PLAN    → planning-and-task-breakdown
BUILD   → incremental-implementation + test-driven-development + source-driven-development
VERIFY  → debugging-and-error-recovery
REVIEW  → code-review-and-quality + security-and-hardening + doubt-driven-development
SHIP    → git-workflow-and-versioning + ci-cd-and-automation + shipping-and-launch
```

## Critical Skills for Bounty Hunter

### 1. `security-and-hardening` (mandatory for all code)

Bounty hunter handles:
- Untrusted scraped HTML (XSS, injection in parsed data)
- AI-generated output (prompt injection, malicious code in PoCs)
- API keys (Gemini, Groq, GitHub PAT, Etherscan)
- Wallet addresses (never private keys)

**Every PR must pass the security checklist in `references/security-checklist.md`.**

### 2. `doubt-driven-development` (mandatory for findings before submission)

Before any vulnerability finding is submitted to a platform:
1. AI generates finding (claim)
2. Second AI pass extracts assumptions
3. Third AI pass doubts the finding (adversarial review)
4. Human reviews the reconciled output
5. Only then `/submit` is allowed

This prevents false-positive submissions that damage reputation.

### 3. `source-driven-development` (for Web3 frameworks)

When integrating Slither, Foundry, web3.py, or any Web3 library:
- Verify against official docs
- Cite source URLs in code comments
- Flag anything unverified

### 4. `test-driven-development` (for all logic)

Red-Green-Refactor. No exceptions for:
- Scraper parsers (test with cached HTML fixtures)
- AI prompt templates (test with mocked AI responses)
- State management (test dedup, TTL, concurrent access)
- Severity classification (test all severity levels per platform)

## Anti-Rationalization

The following thoughts are incorrect and must be ignored:

- "This is too small for a skill" — invoke anyway
- "I can just quickly implement this" — no, follow the skill
- "I'll gather context first" — context-gathering IS the skill's first step
- "Tests can come later" — TDD is non-negotiable
- "AI output is probably safe" — treat as untrusted per `security-and-hardening`
- "This finding looks solid, submit it" — run `doubt-driven-development` first

## Operating Behaviors (from `skills/using-agent-skills/SKILL.md`)

1. **Surface assumptions** — list them explicitly before implementing
2. **Manage confusion actively** — STOP when confused, don't guess
3. **Push back when warranted** — sycophancy is a failure mode
4. **Enforce simplicity** — prefer boring, obvious solutions
5. **Maintain scope discipline** — touch only what's asked
6. **Verify, don't assume** — evidence required, "seems right" is insufficient

## Boundaries (from `SPEC.md`)

### Always do:
- Run `pytest` + `ruff check` before every commit
- Validate all external input (scraped HTML, AI output) at boundaries
- Treat all AI output as untrusted — never submit without human review
- Use `skills/security-and-hardening/` checklist for security-sensitive code
- Apply `doubt-driven-development` before any submission

### Ask first:
- Adding new bounty platform scrapers (TOS review)
- Changing AI prompt templates (quality impact)
- Auto-submitting reports without `/approve`
- Adding new dependencies (supply-chain risk)
- Modifying GitHub Actions workflows

### Never do:
- Submit reports without explicit human `/approve`
- Commit API keys, wallet private keys, session cookies
- Use AI-generated PoCs without local testing
- Skip `doubt-driven-development` for high-severity findings
- Auto-merge PRs without code review
- Store wallet private keys anywhere

## Personas (from `agents/`)

Four specialist personas available for targeted reviews:

| Persona | Role | When to use |
|---------|------|-------------|
| `agents/security-auditor.md` | Security Engineer | Before any submission — vulnerability assessment |
| `agents/code-reviewer.md` | Senior Staff Engineer | Before any merge — five-axis code review |
| `agents/test-engineer.md` | QA Specialist | Test strategy + coverage analysis |
| `agents/web-performance-auditor.md` | Web Performance Engineer | (less relevant for this project) |

**Composition rule:** the user (or slash command) is the orchestrator. Personas do not invoke other personas. See `references/orchestration-patterns.md`.

## Repository Layout

See `SPEC.md` → "Project Structure" section for full layout.

Key directories:
- `skills/` — 24 vendored skills (do not modify unless upgrading)
- `agents/` — 4 specialist personas
- `references/` — 7 supplementary checklists
- `src/` — application code (scrapers, analyzers, reporters, trackers, utils)
- `tests/` — pytest suite mirroring `src/`
- `tasks/` — planning artifacts (`plan.md`, `todo.md`)
- `state/` — runtime state (gitignored, never committed)
- `docs/` — documentation + vuln-patterns knowledge base
