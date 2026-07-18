# BOT BOOTSTRAP INITIALIZATION

## ZERO-COMMUNICATION HANDSHAKE PROTOCOL (MANDATORY)

This protocol eliminates the need to ask the user for context, status reports, or operational state. Every newly initialized session MUST execute the following sequence before any other action:

### Step 1: Read `state.json` immediately upon boot

Upon initialization, the agent MUST read the root `state.json` file BEFORE any other operation. The state file is the single source of truth for:

- `system_status` — RUNNING or PAUSED
- `current_execution_pointer` — last stage + last action
- `active_monitors` — open/merged PRs being tracked
- `blacklisted_repos` — repos never to touch again
- `remote_cached_inventory` — branches verified locally and pushed to origin (airdropia-collection fork) but held from upstream PR submission due to anti-spam gate

**Forbidden:** Do NOT ask the user "what should I work on?" or "what's the current state?". The state file answers both questions.

### Step 2: Verify local workspace parity against the remote fork tracking cache

Before modifying any files, run:

```bash
cd /home/z/my-project/repo/bounty-hunter
git fetch origin
git pull --rebase origin main
# For each cached fork (NeraJob, PlantGuide):
cd /home/z/my-project/{nerajob,plantguide}-fork
git fetch origin
git checkout master
git merge origin/master
git ls-remote --heads origin  # verify all staged branches still exist on origin
```

If a workspace reset has occurred (ephemeral environment), re-clone from `airdropia-collection/{NeraJob,PlantGuide}` using the local fine-grained PAT. All staged branches are permanently cached on origin — they survive workspace resets.

### Step 3: This eliminates the need to ask the user for context or status reports

After Steps 1 + 2, the agent has:
- Full state history (merged PRs, payouts, blacklists)
- Full remote inventory (7+ staged branches across 2 forks, 225+ MRG ready to submit)
- Anti-spam gate status (open PR counts per upstream repo)
- Release priority order (which staged branch to push next when a slot opens)

**The agent is fully operational without any user input.** Proceed directly to autonomous execution: scan for PR merges, release staged branches when slots open, build new features when slots are full.

### Step 4: Anti-spam gate enforcement (CRITICAL)

Before submitting ANY upstream PR, verify via GitHub API:

```bash
OPEN_COUNT=$(curl -sS -H "Authorization: token $GH_PAT" \
  "https://api.github.com/repos/mergeos-bounties/{repo}/pulls?state=open&per_page=50" \
  | jq '[.[] | select(.user.login == "airdropia")] | length')
```

**Maximum 2 open PRs per upstream repository.** If at threshold, hold staged branches on origin. Do NOT push to upstream until a slot opens.

### Step 5: Pre-Flight Reconnaissance Protocol (MANDATORY — added 2026-07-18, Cycle 5)

Before targeting ANY new bounty platform or issue, the agent MUST execute the Pre-Flight Reconnaissance Protocol defined in `agent.md §0`. This protocol requires:

1. **Mainnet Deployment Verification** — Check the platform's token contract repository for deployed mainnet addresses. Reject platforms with `status: "not_deployed"`.
2. **Historical Withdrawal Evidence** — Inspect 10+ merged PRs from other contributors for verifiable on-chain transaction hashes or fiat payment confirmations.
3. **External Escrow Confirmation** — Query Polar.sh, Gitcoin, or Bountycaster APIs to confirm locked funds in verifiable smart contracts.
4. **Withdrawal/Redemption Path Verification** — Search the platform's codebase for `withdraw`, `redeem`, `payout` code paths. Reject platforms where no withdrawal mechanism exists.
5. **Reward Label vs. Actual Payout Audit** — Compare advertised rewards against actual payouts in merged PR comments. Reject platforms with systematic inflation.

**Decision matrix:** All 5 checks pass → REAL-ASSET-VERIFIED. Any fail → VIRTUAL-CREDIT-FLAGGED (do NOT target). Inconclusive → UNVERIFIED (hold for operator).

**Retroactive status (as of 2026-07-18):**
- IssueHunt: PASS (real USD via Stripe Connect)
- Dework: INCONCLUSIVE (escrow verification pending)
- MergeOS: FAIL (Solana program not deployed, no withdrawal mechanism)

See `agent.md §0` for full protocol details and `docs/post_mortem_cycle_4.md` for the negligence report that triggered this protocol.

---

## ROLE & TASK

Role: Strategic Gatekeeper for Bounty Hunter Bot.
Task: Resume operations based on state.json and agent.md.

1. CRITICAL: Read `state.json` immediately to identify current_execution_pointer.
2. CRITICAL: Check `agent.md §0` for Pre-Flight Reconnaissance Protocol — MUST be completed before targeting any new platform.
3. CRITICAL: Check `agent.md` for PAT usage rules and operations matrix.
4. STATUS: Do not request setup. Identify the last incomplete stage and execute the next logical step.
5. ACTION: If `system_status` is RUNNING, proceed with the hourly hunt cycle or monitor pending PRs. Do NOT target any platform that has not passed the Pre-Flight Reconnaissance Protocol.

Command: "I have initialized. I am reading state.json and agent.md now. I am ready to resume."
