# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Project scaffolding: `pyproject.toml`, `requirements.txt`, `.gitignore`, `.env.example`, `LICENSE`, `README.md`
- Vendored all 24 skills from `addyosmani/agent-skills` in `skills/`
- Vendored 4 specialist personas in `agents/` (security-auditor, code-reviewer, test-engineer, web-performance-auditor)
- Vendored 7 reference checklists in `references/`
- `AGENTS.md` — AI agent operating rules with intent → skill mapping
- `SPEC.md` — full project specification (objective, tech stack, structure, boundaries, success criteria)
- `tasks/plan.md` — implementation plan with 25 tasks across 5 phases
- `tasks/todo.md` — atomic task checklist with acceptance criteria
- Directory structure: `src/{scrapers,analyzers,reporters,trackers,utils}`, `tests/`, `state/`, `cache/`, `docs/`

### Planned (Phase 1-5)
- Core utilities (logger, sanitizer, state, retry) — port from microwork-hunter
- Config module + health check CLI
- GitHub client wrapper (Issues, PRs)
- Immunefi, Code4rana, Sherlock, Gitcoin scrapers
- AI helper (Gemini → Groq fallback)
- Contract downloader + Slither integration
- AI vulnerability detector + severity classifier
- Doubt-driven review (adversarial second-pass)
- Report drafter + PoC generator
- GitHub Issue creator + review-bot workflow
- Submission tracker + earnings tracker
- Daily hunt workflow (GitHub Actions, every 6h)
- Documentation (ROADMAP, CONTRIBUTING, SECURITY)

## [0.1.0] — 2026-07-15

### Added
- Initial project structure
- Spec-driven development baseline (SPEC.md, tasks/plan.md, tasks/todo.md)
- agent-skills vendored (24 skills, 4 agents, 7 references)
- MIT License
