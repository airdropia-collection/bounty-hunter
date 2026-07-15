# Contributing to Bounty Hunter

First off — thank you for contributing! 🎉

This project follows the **agent-skills** workflow. Every contribution goes through the skill-driven lifecycle.

---

## 🧠 Skill-Driven Workflow

Before writing any code, check [`AGENTS.md`](AGENTS.md) for the intent → skill mapping. The short version:

| What you're doing | Skill to invoke |
|-------------------|-----------------|
| New feature | `skills/spec-driven-development/` → update SPEC.md first |
| Breaking down work | `skills/planning-and-task-breakdown/` → update tasks/ |
| Writing code | `skills/incremental-implementation/` + `skills/test-driven-development/` |
| Fixing a bug | `skills/debugging-and-error-recovery/` |
| Reviewing code | `skills/code-review-and-quality/` |
| Security-sensitive code | `skills/security-and-hardening/` (mandatory) |
| High-stakes decision | `skills/doubt-driven-development/` |
| Committing | `skills/git-workflow-and-versioning/` |

**If a skill applies (even 1% chance), invoke it.** Do not implement directly.

---

## 🚀 Quick Start for Contributors

```bash
# 1. Fork & clone
git clone https://github.com/<your-username>/bounty-hunter.git
cd bounty-hunter

# 2. Virtual env & install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

# 3. Configure
cp .env.example .env
# Edit .env: add GEMINI_API_KEY, GROQ_API_KEY (GH_PAT optional for local dev)

# 4. Run tests
pytest -v

# 5. Lint
ruff check src tests

# 6. Run pipeline (dry-run)
python -m src.pipeline --dry-run
```

---

## 📝 Commit Message Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat:     new feature
fix:      bug fix
docs:     documentation only
refactor: code change that neither fixes a bug nor adds a feature
test:     adding tests
chore:    build / ci / tooling
sec:      security fix
```

Example: `feat: add Immunefi scraper with payout tier parsing`

---

## 🔀 Pull Request Process

1. **Branch name:** `<type>/<short-description>` (e.g., `feat/immunefi-scraper`)
2. **Keep changes small** — ~100 lines per PR (per `skills/git-workflow-and-versioning/`)
3. **Open PR against `main`**
4. **CI must be green** (lint + tests)
5. **Apply security checklist** if touching scrapers, AI prompts, or key handling
6. **Squash-merge** only (configured at repo level)
7. Branch auto-deleted on merge

For substantial changes (>200 LOC or new platform scraper), please open an issue first to discuss the design.

---

## 🧪 Testing Conventions

- **All utility functions must have tests** — `pytest` + `respx` for HTTP mocking
- **Scraper tests use cached HTML fixtures** in `tests/fixtures/`
- **AI tests mock the AI calls** — never hit real Gemini/Groq in unit tests
- **Integration tests** (marked `@pytest.mark.integration`) hit real endpoints, run separately

Run tests:
```bash
pytest -v                    # unit tests only
pytest --integration         # include integration tests
pytest --cov=src             # with coverage
```

---

## 🎨 Coding Standards

- **Python 3.11+** (`from __future__ import annotations` for forward refs)
- **Type hints** mandatory on all public functions
- **`ruff`** for linting — config in `pyproject.toml`
- **No `print()` in production code** — use `logging` via `src/utils/logger.py`
- **No bare `except:`** — catch `Exception` at minimum
- **Dataclasses** for all data structures (not dicts)
- **Docstrings** on every class and non-trivial function

---

## 🔐 Security-Sensitive Contributions

If your PR touches:
- Scrapers (parsing untrusted HTML)
- AI prompts (handling AI output)
- Key/secret management
- `/submit` `/reject` command handling
- GitHub webhook processing

**You must:**
1. Apply `skills/security-and-hardening/` checklist
2. Add tests for the security boundary
3. Note the security implications in your PR description
4. Be prepared for a deeper review

---

## 🐛 Reporting Bugs

Open an issue using the **Bug Report** template. Include:
- Platform affected (Immunefi/Code4rana/Sherlock/Gitcoin)
- Workflow run URL (if applicable)
- Log excerpt (redact any secrets)
- Reproduction steps

---

## ❓ Questions

Open a [GitHub Discussion](https://github.com/airdropia-collection/bounty-hunter/discussions).

Happy hunting! 🎯
