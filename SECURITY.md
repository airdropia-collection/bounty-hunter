# Security Policy

## 🔐 Reporting a Vulnerability

This project handles API keys, AI-generated output, and interacts with financial platforms. A vulnerability could leak credentials or cause incorrect bounty submissions.

**If you discover a vulnerability, please DO NOT open a public issue.** Instead:

1. Open a private security advisory via GitHub:
   👉 https://github.com/airdropia-collection/bounty-hunter/security/advisories/new
2. Include: description, steps to reproduce, affected files, suggested fix
3. We will respond within 72 hours

---

## 🛡️ Threat Model

This project follows the threat-modeling process in `skills/security-and-hardening/SKILL.md`.

### Trust Boundaries

| Boundary | Untrusted Input | Risk |
|----------|-----------------|------|
| Scraped HTML | Immunefi/Code4rana/Sherlock pages | XSS in parsed data, injection in downstream processing |
| AI output | Gemini/Groq responses | Prompt injection, malicious PoC code, false-positive findings |
| GitHub webhook | Issue comment bodies | Command injection in `/submit` `/reject` parsing |
| External RPC | Web3 RPC responses | Malicious contract bytecode, RPC poisoning |
| Config files | `.env`, secrets | Credential leak if committed |

### Assets

| Asset | Protection |
|-------|------------|
| API keys (Gemini, Groq, Etherscan) | Environment variables only, never in code, sanitizer on logs |
| GitHub PAT | Fine-grained, scoped to this repo only, rotated quarterly |
| Wallet address | Public by nature — but never store private keys |
| Findings database | `state/findings.json` — gitignored, contains pre-disclosure vulnerabilities |
| Submitted reports | `state/submissions.json` — tracks what was disclosed where |

### STRIDE Analysis

| Threat | Apply to | Mitigation |
|--------|----------|------------|
| **S**poofing | GitHub webhook (fake issue comments) | Validate webhook signature, check commenter is repo collaborator |
| **T**ampering | Scraped HTML, AI output | Parse defensively, validate all fields, never `eval()` AI output |
| **R**epudiation | Submissions | Audit log in `state/submissions.json` with timestamps |
| **I**nformation disclosure | Findings before submission | `state/` gitignored, findings never in commit messages, sanitizer on logs |
| **D**enial of service | AI token usage, RPC calls | Rate limits, token caps, daily quotas, circuit breakers |
| **E**levation of privilege | `/submit` command | Only repo owner can submit; check `commenter.login == repo.owner` |

---

## 🚨 If You Leak a Secret

### API key leaked (Gemini/Groq/Etherscan)
1. Revoke immediately at provider's dashboard
2. Generate new key
3. Update GitHub Secret
4. Audit logs for unauthorized usage

### GitHub PAT leaked
1. https://github.com/settings/tokens → delete the token
2. Generate new fine-grained PAT (scoped to this repo only)
3. Update `GH_PAT` GitHub Secret
4. Check repo audit log for unauthorized commits/PRs

### Wallet private key leaked (should NEVER happen)
1. **Immediately** move all funds to a new wallet
2. Treat the old wallet as compromised forever
3. Update `WALLET_ADDRESS` secret if needed

### Pre-disclosure vulnerability leaked
1. Do NOT commit `state/findings.json` (it's gitignored)
2. If accidentally committed: force-push to remove, then notify the affected project
3. Follow coordinated disclosure per the platform's TOS

---

## 🔍 Secret Scanning

`.gitignore` blocks:
```
.env, .env.local, *.pem, *.key, *pat*, *token*, .secrets/
state/, cache/, evidence/, reports/
```

If you must commit a test fixture with fake secrets, prefix with `fake_` or `example_` and use obviously synthetic values.

---

## 🤖 AI-Specific Security (per `skills/security-and-hardening/`)

This project uses LLMs (Gemini, Groq). Per OWASP Top 10 for LLM Applications:

- **Treat all AI output as untrusted** — never `eval()`, never pass to shell, never inject into SQL
- **Assume prompt injection** — scraped HTML may contain "ignore previous instructions"
- **No secrets in prompts** — API keys, wallet keys never sent to AI
- **Bound consumption** — token caps, rate limits, max loop depth
- **Human gate** — `/submit` requires human approval, never auto-submits

---

## 📜 Responsible Disclosure

This project submits vulnerability reports to platforms (Immunefi, Code4rana, etc.). We follow each platform's disclosure rules:

- **Immunefi:** Coordinated disclosure after fix deployed
- **Code4rana:** Contest reports are private until contest ends
- **Sherlock:** Same as Code4rana
- **Gitcoin:** Per bounty issuer's rules

**We never publicly disclose vulnerabilities before the platform allows it.**

---

## 📋 Security Checklist (per `references/security-checklist.md`)

Before every PR that touches security-sensitive code:

- [ ] No secrets in code (`git diff --cached | grep -i "password\|secret\|api_key\|token"`)
- [ ] `.gitignore` covers all secret patterns
- [ ] All external input validated at boundaries
- [ ] AI output treated as untrusted (no eval, no shell, no SQL)
- [ ] No `state/` files committed (pre-disclosure findings)
- [ ] Rate limits on all external calls
- [ ] Error messages don't expose internals
- [ ] `/submit` command checks commenter authorization
- [ ] Tests cover security-sensitive paths
