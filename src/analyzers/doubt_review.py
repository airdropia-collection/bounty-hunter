"""
Rigorous adversarial finding verifier.

Implements the 10-step verification process:
  1. Ignore AI's confidence score
  2. Resolve complete inheritance chain
  3. Resolve all imported files
  4. Find exact implementation of every referenced function/modifier
  5. Build the call graph
  6. Determine whether code is actually reachable
  7. Explain why compilation succeeds or fails
  8. Search for code that contradicts the claim
  9. Attempt to falsify the finding before accepting
  10. Only mark SUBMITTABLE if it survives ALL steps

Output per finding:
  - VERIFIED (with evidence)
  - FALSE_POSITIVE (with evidence)
  - INCONCLUSIVE (with what's missing)

This is NOT a "do you doubt this?" prompt. This is a forensic code audit.
The AI must PROVE or DISPROVE with exact file paths, line numbers,
inheritance chains, and call graphs.

Skills applied: skills/doubt-driven-development/
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.analyzers.ai_helper import get_ai_helper
from src.analyzers.vuln_detector import Finding
from src.utils.logger import get_logger
from src.utils.sanitizer import sanitize

log = get_logger("verifier")


@dataclass
class VerifiedFinding:
    """A finding after rigorous 10-step verification."""
    original: Finding
    verdict: str  # "VERIFIED" | "FALSE_POSITIVE" | "INCONCLUSIVE"
    evidence: str  # detailed technical evidence
    inheritance_chain: str  # resolved inheritance
    call_graph: str  # resolved call graph
    falsification_attempts: str  # what was tried to disprove
    recommendation: str  # "submit" | "investigate" | "discard"
    confidence_adjusted: float  # 0.0-1.0, recalculated by verifier

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original.to_dict(),
            "verdict": self.verdict,
            "evidence": self.evidence,
            "inheritance_chain": self.inheritance_chain,
            "call_graph": self.call_graph,
            "falsification_attempts": self.falsification_attempts,
            "recommendation": self.recommendation,
            "confidence_adjusted": self.confidence_adjusted,
        }


# The verification prompt — this is the heart of the system.
# It forces the AI to act as a forensic code auditor, not a yes-man.
VERIFICATION_PROMPT = """You are a forensic smart contract code auditor.
Your job is to PROVE or DISPROVE the following vulnerability finding.

Gemini's finding is NOT an authority. Treat it as an untrusted hypothesis.
Your job is to either PROVE it or DISPROVE it with code evidence.

## Finding to verify:
- Title: {title}
- Severity: {severity}
- Description: {description}
- Impact: {impact}
- SWC ID: {swc_id}

## Full source code:
```solidity
{code}
```

## Your verification process (ALL 10 steps are mandatory):

### Step 1: Ignore the AI's confidence score
The AI said confidence={confidence}. IGNORE THIS. Start from zero.
The confidence is meaningless until you verify with code.

### Step 2: Resolve the complete inheritance chain
For every contract involved, list ALL parent contracts.
Example: AgentVault → ReentrancyGuard, UUPSUpgradeable, IIAgentVault, IERC165
Trace each parent to its source (OpenZeppelin? Custom? Interface only?).

### Step 3: Resolve all imported files
List every `import` statement. For each:
- Is it from OpenZeppelin? Which version?
- Is it a custom file? Is its source available?
- Is it missing? (Missing = can't verify)

### Step 4: Find exact implementation of every referenced function/modifier
For every function/modifier mentioned in the finding:
- Where is it defined? (exact contract, exact line)
- Is it inherited? From which parent?
- Is it ABSTRACT (no implementation)? → finding is INCONCLUSIVE
- Is it MISSING entirely? → finding might be VERIFIED (broken modifier)

### Step 5: Build the call graph
For the vulnerable function, trace:
- Who calls it? (external users? other contracts? internal?)
- What does it call? (external contracts? internal functions?)
- Is the vulnerable path REACHABLE from an external call?

### Step 6: Determine reachability
- Can an attacker actually reach this code path?
- Are there access controls that prevent it?
- Is the function `external`? `public`? `internal`?
- Is it behind a proxy? Does that change things?

### Step 7: Explain compilation
- Would this code even compile? (missing functions = compile error)
- If it can't compile, the finding might be about UNVERIFIED code
- Solidity does NOT allow calling undefined functions

### Step 8: Search for contradicting code
Actively look for code that DISPROVES the finding:
- Is there a fallback that implements the missing function?
- Is there a `virtual` override somewhere?
- Is there a library that provides the implementation?
- Is the modifier actually defined in a way the AI missed?

### Step 9: Attempt falsification
Before accepting, try to BREAK the finding:
- "What if the function is defined in a file I can't see?" → INCONCLUSIVE
- "What if OpenZeppelin's UUPSUpgradeable provides isOwner()?" → check
- "What if there's a proxy delegatecall that changes everything?" → check
- "What if the code shown is incomplete (truncated)?" → note it

### Step 10: Final verdict
Only if the finding survives ALL 9 steps, mark it VERIFIED.
If you found contradicting evidence, mark it FALSE_POSITIVE.
If you can't verify (missing code, truncated source), mark it INCONCLUSIVE.

## Output format (JSON):
{{
  "verdict": "VERIFIED" | "FALSE_POSITIVE" | "INCONCLUSIVE",
  "evidence": "Detailed technical evidence with exact line references, contract names, and code snippets that prove or disprove the finding.",
  "inheritance_chain": "Full inheritance chain for all contracts involved, with source of each parent.",
  "call_graph": "Who calls what, is the vulnerable path reachable from external calls.",
  "falsification_attempts": "What you tried to disprove the finding and why it failed (for VERIFIED) or succeeded (for FALSE_POSITIVE).",
  "recommendation": "submit" | "investigate" | "discard",
  "confidence_adjusted": 0.0-1.0,
  "compilation_note": "Would this code compile? If not, what's missing?"
}}

RULES:
- NEVER say "submit" for INCONCLUSIVE findings
- NEVER accept a finding without code evidence
- NEVER trust the AI's original confidence
- ALWAYS cite exact line numbers and contract names
- If source is truncated/incomplete, say INCONCLUSIVE
- If a function is truly missing and would break compilation, explain WHY
"""


class FindingVerifier:
    """Rigorous 10-step finding verifier."""

    def __init__(self, max_code_chars: int = 8000):
        self.ai = get_ai_helper()
        self.max_code_chars = max_code_chars

    def verify(self, finding: Finding, source_code: str = "") -> VerifiedFinding:
        """Verify a single finding with the 10-step process.

        This is NOT "do you doubt this?" — this is a forensic audit.
        The AI must PROVE or DISPROVE with code evidence.
        """
        code = source_code[: self.max_code_chars] if source_code else "(source not available)"

        prompt = VERIFICATION_PROMPT.format(
            title=finding.title,
            severity=finding.severity,
            confidence=finding.confidence,
            description=finding.description,
            impact=finding.impact,
            swc_id=finding.swc_id or "N/A",
            code=code,
        )

        system = (
            "You are a forensic smart contract auditor. You PROVE or DISPROVE "
            "vulnerability findings with code evidence. You never accept a "
            "finding without verifying it against the actual source code. "
            "You actively try to FALSIFY every finding before accepting it."
        )

        try:
            result = self.ai.generate_json(prompt, system)

            verdict = result.get("verdict", "INCONCLUSIVE")
            confidence_adj = float(result.get("confidence_adjusted", 0.0))

            # Determine recommendation based on verdict
            recommendation = result.get("recommendation", "discard")
            if recommendation not in ("submit", "investigate", "discard"):
                if verdict == "VERIFIED" and confidence_adj >= 0.7:
                    recommendation = "submit"
                elif verdict == "VERIFIED":
                    recommendation = "investigate"
                elif verdict == "INCONCLUSIVE":
                    recommendation = "investigate"
                else:  # FALSE_POSITIVE
                    recommendation = "discard"

            verified = VerifiedFinding(
                original=finding,
                verdict=verdict,
                evidence=result.get("evidence", "No evidence provided"),
                inheritance_chain=result.get("inheritance_chain", "Not resolved"),
                call_graph=result.get("call_graph", "Not built"),
                falsification_attempts=result.get("falsification_attempts", "Not attempted"),
                recommendation=recommendation,
                confidence_adjusted=confidence_adj,
            )

            log.info(
                "verifier: '%s' -> %s (confidence=%.2f recommend=%s)",
                finding.title, verdict, confidence_adj, recommendation,
            )
            return verified

        except Exception as exc:
            log.error("verification failed: %s", sanitize(exc))
            # On error, be conservative — don't submit
            return VerifiedFinding(
                original=finding,
                verdict="INCONCLUSIVE",
                evidence=f"Verification failed: {exc}",
                inheritance_chain="Not resolved",
                call_graph="Not built",
                falsification_attempts="Not attempted (error)",
                recommendation="discard",
                confidence_adjusted=0.0,
            )

    def verify_many(self, findings: list[Finding], source_code: str = "") -> list[VerifiedFinding]:
        """Verify multiple findings. Adds delay between calls to respect rate limits."""
        import time as _time

        results = []
        for i, finding in enumerate(findings):
            verified = self.verify(finding, source_code)
            results.append(verified)
            # Sleep 5s between verifications to stay under Gemini's 20 req/min
            if i < len(findings) - 1:
                _time.sleep(5)
        return results

    def filter_submittable(self, verified: list[VerifiedFinding]) -> list[VerifiedFinding]:
        """Return only VERIFIED findings recommended for submission."""
        return [v for v in verified if v.verdict == "VERIFIED" and v.recommendation == "submit"]

    def filter_worth_reviewing(self, verified: list[VerifiedFinding]) -> list[VerifiedFinding]:
        """Return VERIFIED + INCONCLUSIVE findings (worth human review)."""
        return [v for v in verified if v.verdict != "FALSE_POSITIVE"]
