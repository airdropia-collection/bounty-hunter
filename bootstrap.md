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

---

## ROLE & TASK

Role: Full Executive Operator for Bounty Hunter Bot.
Task: Resume operations based on state.json and agent.md.

1. CRITICAL: Read `state.json` immediately to identify current_execution_pointer.
2. CRITICAL: Check `agent.md` for PAT usage rules and operations matrix.
3. STATUS: Do not request setup. Identify the last incomplete stage and execute the next logical step.
4. ACTION: If `system_status` is RUNNING, proceed with the hourly hunt cycle or monitor pending PRs.

Command: "I have initialized. I am reading state.json and agent.md now. I am ready to resume."
