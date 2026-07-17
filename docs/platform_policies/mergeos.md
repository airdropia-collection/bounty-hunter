# MergeOS Bounty Platform — 4-Gate Policy

**Source:** Maintainer directive on PR #252 (mergeos-bounties/Loru), 2026-07-17
**Status:** Active policy enforced by @TUPM96 (Pham Minh Tu)
**Bot compliance:** `src/utils/platform_onboarding.py` → `PLATFORM_REQUIREMENTS["mergeos"]`

---

## ⚠️ Why this doc exists

On 2026-07-17, our bot submitted PR #252 to `mergeos-bounties/Loru` without
completing the platform's required onboarding ritual. The maintainer
blocked the PR with this comment:

> @airdropia **Gate 1 (badges)** blocked on `mergeos-bounties/Loru`.
>
> | Badge | Status |
> | --- | --- |
> | star / follow | **missing** (core stars **+** org follow — **not** only this product repo) |
>
> Starring only `mergeos-bounties/Loru` (or any single product) is **not** enough.
>
> **Order:** badges → security → tests → merge.

This doc captures the policy so the bot NEVER repeats this mistake.

---

## The 4 Gates

MergeOS enforces a strict 4-gate pipeline. **PRs cannot be merged until all
gates pass, in order.**

```
Gate 1: Badges    → follow org + star BOTH core repos
                    (auto-verifiable via GitHub API)
                              ↓
Gate 2: Security  → security review by maintainer
                    (manual; bot has no control)
                              ↓
Gate 3: Tests     → all CI tests pass + maintainer signs off
                    (bot should ensure tests pass locally before PR)
                              ↓
Gate 4: Merge     → maintainer merges PR + bounty payout triggers
                    (auto on IssueHunt-linked bounties)
```

---

## Gate 1 — Badges (the bot's responsibility)

### Required actions

All three actions below MUST be completed BEFORE the bot submits any PR
to any repo under the `mergeos-bounties/` org.

1. **Follow the org**
   - URL: https://github.com/mergeos-bounties
   - API: `PUT /user/following/mergeos-bounties`
   - Required PAT scope: `user:follow` (Classic) OR `Followers` (fine-grained)

2. **Star core repo #1**
   - URL: https://github.com/mergeos-bounties/mergeos
   - API: `PUT /user/starred/mergeos-bounties/mergeos`
   - Required PAT scope: `public_repo` (Classic) OR `Starring` (fine-grained)

3. **Star core repo #2**
   - URL: https://github.com/mergeos-bounties/mergeos-contracts
   - API: `PUT /user/starred/mergeos-bounties/mergeos-contracts`
   - Required PAT scope: same as above

### What does NOT count

- ⛔ Starring only the product repo (e.g. `mergeos-bounties/Loru`)
- ⛔ Following only an individual maintainer (must follow the org)
- ⛔ Starring forks (must star the canonical core repos above)

### How the bot verifies

The `platform_onboarding.py` module calls `GET /user/following/{org}` and
`GET /user/starred/{repo}` for each requirement. If any returns 404, the
PR submission is **BLOCKED** and a 🛡️ FILTER Telegram event is emitted
with the exact missing actions.

### PAT scope limitation

The bot's current fine-grained PAT returns HTTP 403 on follow/star
operations. Until the PAT is upgraded (see `docs/PAT_UPGRADE.md` — TODO),
these actions must be performed **manually by the operator** via browser.
The bot will:

1. Detect the missing onboarding via `platform_onboarding.check_onboarding()`
2. Block PR submission automatically
3. Emit a 🛡️ FILTER Telegram event with the 3 manual action URLs
4. Once the operator confirms completion (via Telegram reply or GitHub
   issue comment), the bot will proceed with PR submission

---

## Gate 2 — Security

Manual review by the maintainer. The bot cannot influence this gate
beyond ensuring the PR diff is minimal, well-commented, and contains no
security anti-patterns (hardcoded secrets, dangerous shell calls, etc.).

Pre-PR forensic checks (agent.md §4) cover this:

- ✅ Syntax & compile check
- ✅ Local regression check
- ✅ Security ingestion scan (no hardcoded API keys/credentials)

---

## Gate 3 — Tests

The maintainer runs CI on the PR. The bot should ensure:

1. The fix doesn't break existing tests (run them locally if a test
   suite is present in the upstream repo)
2. New code paths have at least minimal test coverage where applicable
3. The PR body explicitly mentions what was tested and how

---

## Gate 4 — Merge

Maintainer merges the PR. For IssueHunt-linked bounties, the merge
triggers automatic payout to the contributor's IssueHunt account.

The bot's `pr-monitor.yml` workflow watches for the `merged_at` field
every 30 minutes and emits a 🎉 PR MERGED! Telegram alert when it fires.

---

## Escrow / Payout Safety

MergeOS bounties are escrow-funded before the issue is listed. This
means:

- ✅ The bounty amount is guaranteed (no "I'll pay you later" risk)
- ✅ Payout triggers automatically when the PR is merged
- ✅ No need to chase the maintainer for payment

This is why MergeOS is on the verified-escrow-platforms list (alongside
IssueHunt and Bountycaster).

---

## Operator Action Template

When the bot blocks a MergeOS PR submission due to missing onboarding,
the operator should:

1. Open these 3 URLs in browser (logged in as `airdropia`):
   - https://github.com/mergeos-bounties → click **Follow**
   - https://github.com/mergeos-bounties/mergeos → click **Star**
   - https://github.com/mergeos-bounties/mergeos-contracts → click **Star**

2. Take a screenshot of each (or note the timestamp).

3. Comment on the blocked PR with:
   ```markdown
   ## Gate 1 — Onboarding complete

   - [x] Follow https://github.com/mergeos-bounties
   - [x] Star https://github.com/mergeos-bounties/mergeos
   - [x] Star https://github.com/mergeos-bounties/mergeos-contracts

   Completed at <timestamp>. Ready for Gate 2 (security) review.
   ```

4. The maintainer will verify and unblock Gate 2.

---

## Future Platform Additions

When MergeOS (or any platform) adds new onboarding requirements, update:

1. `src/utils/platform_onboarding.py` → `PLATFORM_REQUIREMENTS[<platform>]`
2. This doc with the new requirement
3. The bot's Telegram 🛡️ FILTER message template will auto-include it

The `platform_onboarding.py` module is the single source of truth —
all checks flow through it.
