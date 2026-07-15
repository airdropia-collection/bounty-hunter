# 🎯 Bounty Hunter

> AI-powered Web3 bug bounty hunter — scrapes Immunefi/Code4rana/Sherlock, analyzes smart contracts with Gemini/Groq, drafts vulnerability reports, and tracks submissions. Runs on GitHub Actions free tier. $0 budget.

[![CI](https://github.com/airdropia-collection/bounty-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/airdropia-collection/bounty-hunter/actions/workflows/ci.yml)
[![Hunt](https://github.com/airdropia-collection/bounty-hunter/actions/workflows/hunt.yml/badge.svg)](https://github.com/airdropia-collection/bounty-hunter/actions/workflows/hunt.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 🎯 What This Does

**Bounty Hunter** is an AI-powered system that:

1. **Scrapes** active bounties from Web3 platforms (Immunefi, Code4rana, Sherlock, Gitcoin)
2. **Filters** bounties by feasibility — AI estimates difficulty vs. payout
3. **Analyzes** smart contract source code with AI + Slither (static analysis)
4. **Drafts** vulnerability reports with severity, impact, PoC, and remediation
5. **Creates GitHub Issues** for each promising finding → you review and approve
6. **Tracks** submission status across platforms (submitted, accepted, paid, rejected)
7. **Learns** from past findings — accumulates a knowledge base of vulnerability patterns

**Your role:** Review the GitHub Issue on your phone → comment `/submit` or `/reject` → done.

---

## 🧠 Built on agent-skills

This repo vendors all 24 skills from [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills):

```
DEFINE          PLAN           BUILD          VERIFY         REVIEW          SHIP
┌──────┐      ┌──────┐      ┌──────┐      ┌──────┐      ┌──────┐      ┌──────┐
│ Idea │ ───▶ │ Spec │ ───▶ │ Code │ ───▶ │ Test │ ───▶ │  QA  │ ───▶ │  Go  │
│Refine│      │  PRD │      │ Impl │      │Debug │      │ Gate │      │ Live │
└──────┘      └──────┘      └──────┘      └──────┘      └──────┘      └──────┘
```

Every task follows the skill workflow. See [`AGENTS.md`](AGENTS.md) for the full mapping.

**Critical skills for this project:**
- `skills/security-and-hardening/` — mandatory for all code (we handle untrusted HTML, AI output, API keys)
- `skills/doubt-driven-development/` — mandatory before any submission (adversarial review of findings)
- `skills/spec-driven-development/` — see [`SPEC.md`](SPEC.md)
- `skills/planning-and-task-breakdown/` — see [`tasks/plan.md`](tasks/plan.md) + [`tasks/todo.md`](tasks/todo.md)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Actions (every 6h)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   SCRAPERS      │   │   ANALYZERS     │   │   REPORTERS     │
│                 │   │                 │   │                 │
│ • Immunefi      │──▶│ • AI (Gemini)   │──▶│ • Draft report  │
│ • Code4rana     │   │ • AI (Groq)     │   │ • PoC generator │
│ • Sherlock      │   │ • Slither       │   │ • GitHub Issue  │
│ • Gitcoin       │   │ • Doubt review  │   │                 │
└─────────────────┘   └─────────────────┘   └────────┬────────┘
                                                     │
                              ┌──────────────────────▼──────────────────────┐
                              │           GitHub Issue created               │
                              │   (you get notification on phone)           │
                              └──────────────────────┬──────────────────────┘
                                                     │
                              ┌──────────────────────▼──────────────────────┐
                              │  You comment: /submit <finding-id>          │
                              │  (or /reject <finding-id> <reason>)         │
                              └──────────────────────┬──────────────────────┘
                                                     │
                              ┌──────────────────────▼──────────────────────┐
                              │           TRACKERS                           │
                              │ • Submission status                          │
                              │ • Earnings tracker                           │
                              └─────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- GitHub account
- Gemini API key (free: https://aistudio.google.com/app/apikey)
- Groq API key (free: https://console.groq.com/)

### Setup

```bash
# 1. Clone
git clone https://github.com/airdropia-collection/bounty-hunter.git
cd bounty-hunter

# 2. Virtual env + install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

# 3. Configure
cp .env.example .env
# Edit .env: add GEMINI_API_KEY, GROQ_API_KEY, GH_PAT

# 4. Health check
python -m src.health

# 5. Run tests
pytest -v

# 6. Run pipeline manually
python -m src.pipeline --dry-run
```

### GitHub Actions (production)

The pipeline runs every 6 hours automatically. To trigger manually:
1. Go to **Actions** tab
2. Select **🎯 Bounty Hunter** workflow
3. Click **Run workflow**
4. Choose: `dry_run=true` (safe, no submissions) or `false` (real submissions)

---

## 📋 Supported Platforms

| Platform | Type | Payout Range | Difficulty |
|----------|------|--------------|------------|
| [Immunefi](https://immunefi.com) | Bug bounty | $500 - $10M | Medium-Hard |
| [Code4rana](https://code4rana.com) | Audit contest | $2k - $50k pot | Medium |
| [Sherlock](https://www.sherlock.xyz) | Audit contest | $5k - $30k pot | Medium |
| [Gitcoin](https://gitcoin.co) | Open-source bounty | $50 - $5k | Easy-Medium |

---

## 🎯 Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for full Day1/Week1/Month1/Year1 targets.

**First milestone:** First $1 earned (~30 days)

---

## 🔐 Security

This project handles:
- Untrusted scraped HTML
- AI-generated output (treated as untrusted per `skills/security-and-hardening/`)
- API keys (Gemini, Groq, GitHub PAT, Etherscan)
- Wallet addresses (NEVER private keys)

See [`SECURITY.md`](SECURITY.md) for the full threat model.

---

## 🤝 Contributing

PRs welcome! Please:
1. Follow the skill workflow in [`AGENTS.md`](AGENTS.md)
2. Run `ruff check` + `pytest` before submitting
3. Keep changes small (~100 lines per PR per `skills/git-workflow-and-versioning/`)
4. Apply `skills/security-and-hardening/` checklist if touching security-sensitive code

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for details.

---

## 📄 License

MIT — see [`LICENSE`](LICENSE)

---

**Budget: $0 · Runs on GitHub Actions free tier · Built with agent-skills**
