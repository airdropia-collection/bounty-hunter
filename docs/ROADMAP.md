# 🎯 Bounty Hunter — Roadmap & Targets

> Honest expectations, realistic milestones, sustainable growth.

## ⚠️ Honest Reality Check

**Bug bounty is NOT easy money.** Here's the truth:

### What this bot CAN do:
- ✅ Scan hundreds of bounties per week (impossible manually)
- ✅ Analyze smart contracts faster than any human
- ✅ Draft reports you'd spend hours writing
- ✅ Never miss a new contest deadline
- ✅ Build a knowledge base of vuln patterns over time

### What this bot CANNOT do:
- ❌ Guarantee payouts (most findings are duplicates or invalid)
- ❌ Replace human judgment (AI makes mistakes — false positives cost reputation)
- ❌ Bypass platform TOS (we play by the rules)
- ❌ Win every contest (top hunters worldwide compete)

### Realistic earnings per platform:

| Platform | Per-Finding Payout | Realistic Monthly |
|----------|-------------------|-------------------|
| Immunefi | $500 - $10M | $0 - $500 (mostly $0 first 3 months) |
| Code4rana | $2k - $50k pot (shared) | $0 - $300 (low severity mostly) |
| Sherlock | $5k - $30k pot (shared) | $0 - $200 |
| Gitcoin | $50 - $5k | $0 - $100 (easiest entry) |

---

## 📅 Phase 0: Foundation (Days 1-3)

### Goals:
- Repo live with full structure
- 24 agent-skills vendored
- SPEC.md + tasks/plan.md + tasks/todo.md written
- CI workflow passes

### Your role:
- Create GitHub repo manually (PAT can't create repos)
- Add secrets: `GEMINI_API_KEY`, `GROQ_API_KEY`, `GH_PAT`
- Review SPEC.md + tasks/plan.md before we start building

### Success criteria:
- [ ] Repo created: https://github.com/airdropia-collection/bounty-hunter
- [ ] Initial commit pushed
- [ ] CI workflow green
- [ ] All 4 secrets added

---

## 📅 Week 1: Pipeline Working (Days 4-7)

### Goals:
- 4 scrapers (Immunefi, Code4rana, Sherlock, Gitcoin) working
- Dedup state functional
- First bounty analyzed end-to-end (mock AI for now)

### Targets:
| Metric | Target |
|--------|--------|
| Scrapers working | 3/4 |
| Bounties scraped (cumulative) | 50+ |
| Tests passing | 30+ |
| AI cost | $0 (within free tier) |
| **Earnings** | **$0** (expected) |

### Success criteria:
- [ ] `python -m src.scrapers.immunefi` returns ≥10 bounties
- [ ] Re-running doesn't duplicate bounties (dedup works)
- [ ] CI green on every commit

---

## 📅 Week 2: AI Analysis (Days 8-14)

### Goals:
- AI helper (Gemini → Groq) working
- Contract downloader (GitHub + Etherscan)
- Slither integration
- First vulnerability findings generated

### Targets:
| Metric | Target |
|--------|--------|
| Bounties analyzed | 10+ |
| Findings generated | 5+ (mostly false positives, expected) |
| Doubt-driven reviews | All High/Critical findings |
| Tests passing | 60+ |
| **Earnings** | **$0** (still expected) |

### Success criteria:
- [ ] At least 1 finding with severity classification
- [ ] `state/findings.json` populated
- [ ] AI token usage tracked and within free tier

---

## 📅 Week 3: Reporting + First Issue (Days 15-21)

### Goals:
- Report drafter with per-platform templates
- PoC generator (Foundry test cases)
- GitHub Issue creator working
- Review-bot responds to `/submit` `/reject`

### Targets:
| Metric | Target |
|--------|--------|
| GitHub Issues created | 1-3 |
| Findings ready for review | 2-5 |
| Review-bot tested | Yes |
| Tests passing | 80+ |
| **Earnings** | **$0** (pipeline complete, no submissions yet) |

### Success criteria:
- [ ] First GitHub Issue created with real finding
- [ ] `/submit` command works (test with mock submission)
- [ ] End-to-end pipeline runs unattended for 24h

---

## 📅 Month 1: First Submission (Days 22-30)

### Goals:
- Submission tracker working
- First real submission to a platform
- First $1 earned (the milestone!)

### Targets:
| Metric | Target |
|--------|--------|
| Submissions made | 1-3 |
| Submissions accepted | 0-1 (realistic) |
| First payout | $1 - $50 |
| Tests passing | 100+ |
| **Earnings** | **$1 - $50** |

### Success criteria:
- [ ] At least 1 submission tracked in `state/submissions.json`
- [ ] Earnings tracker shows > $0
- [ ] Pipeline stable for 7+ days unattended

---

## 📅 Month 3: Sustainable Cadence

### Goals:
- 3-5 submissions per month
- Knowledge base with 10+ vuln patterns
- At least 1 paid bounty ($100+)

### Targets:
| Metric | Target |
|--------|--------|
| Total submissions | 10-15 |
| Accepted submissions | 2-5 |
| Total earnings | $100 - $500 |
| Vuln patterns documented | 10+ |

---

## 📅 Year 1: Real Income

### Goals:
- $1,000+ total earnings
- Reputation on at least 1 platform (top 500 on Immunefi leaderboard)
- Portfolio of 20+ submitted reports

### Targets:
| Metric | Target |
|--------|--------|
| Total submissions | 80-120 |
| Accepted submissions | 15-30 |
| Total earnings | $1,000 - $5,000 |
| Platforms active | 3-4 |

---

## 🚨 Risk Management

### Reputation Risk:
- **High risk:** Submitting invalid reports damages reputation
- **Mitigation:** `doubt-driven-development` skill runs adversarial review before submission
- **Mitigation:** Human `/submit` approval mandatory (never auto-submit)

### AI Cost Risk:
- **Medium risk:** Token usage could exceed free tier if many bounties analyzed
- **Mitigation:** Daily token cap (auto-pause at 80% of quota)
- **Mitigation:** Cache AI responses (same contract = same analysis)

### Platform Ban Risk:
- **Low risk:** We follow TOS, use official APIs where available
- **Mitigation:** Rate-limit scrapers (1 req/sec)
- **Mitigation:** Read each platform's TOS before scraping

### Burnout Risk:
- **Medium risk:** Reviewing false positives is demoralizing
- **Mitigation:** Filter aggressively (min payout, min severity)
- **Mitigation:** Track false-positive rate, tune AI prompts over time

---

## 📊 How to Track Progress

The bot automatically generates:
- `state/bounties_seen.json` — all bounties ever scraped
- `state/findings.json` — AI-discovered findings
- `state/submissions.json` — submitted reports + status
- `state/earnings.json` — lifetime earnings tracker
- `docs/vuln-patterns/` — accumulated knowledge base

After each daily run, check:
1. **Actions tab** — did the run succeed?
2. **Issues** — any new findings to review?
3. **state/earnings.json** — updated earnings?

---

## 🤝 Division of Labor

| Task | Who |
|------|-----|
| Code, architecture, bug fixes, scrapers, AI prompts | **Me (AI assistant)** |
| Adding secrets, reviewing SPEC.md | **You** |
| Reviewing GitHub Issues (findings) | **You** |
| `/submit` or `/reject` decisions | **You** |
| Manual submission to platform (if bot can't) | **You** |
| Strategic decisions (add platform X? change focus?) | **You decide, I implement** |

---

*Last updated: 2026-07-15*
*This is a living roadmap — updated as we learn what works.*
