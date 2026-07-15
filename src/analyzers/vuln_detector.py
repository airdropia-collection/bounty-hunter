"""
AI-powered vulnerability detector + verifier (merged).

Single AI call that:
1. Finds vulnerabilities in Solidity code
2. Immediately verifies each finding with the 10-step process
3. Returns only VERIFIED findings (FALSE_POSITIVEs are discarded)

This merged approach:
- Reduces API calls from 4+ to 1 (avoids Gemini rate limits)
- AI sees both the code AND its own findings in one context
- Verification is more accurate (no context loss between calls)

Skills applied: skills/doubt-driven-development/
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.analyzers.ai_helper import get_ai_helper
from src.utils.logger import get_logger
from src.utils.sanitizer import sanitize

log = get_logger("vuln_detector")


@dataclass
class Finding:
    """A verified vulnerability finding."""
    id: str
    title: str
    severity: str  # Critical | High | Medium | Low | Info
    confidence: float  # 0.0 to 1.0 (VERIFIED confidence, not AI's initial guess)
    description: str
    impact: str
    recommendation: str
    line_numbers: list[str] = field(default_factory=list)
    poc_suggestion: str = ""
    swc_id: str = ""
    verdict: str = "VERIFIED"  # VERIFIED | FALSE_POSITIVE | INCONCLUSIVE
    evidence: str = ""  # verification evidence
    inheritance_chain: str = ""
    call_graph: str = ""
    falsification_attempts: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence,
            "description": self.description,
            "impact": self.impact,
            "recommendation": self.recommendation,
            "line_numbers": self.line_numbers,
            "poc_suggestion": self.poc_suggestion,
            "swc_id": self.swc_id,
            "verdict": self.verdict,
            "evidence": self.evidence,
            "inheritance_chain": self.inheritance_chain,
            "call_graph": self.call_graph,
            "falsification_attempts": self.falsification_attempts,
        }


# Merged prompt: detect + verify in ONE call
MERGED_PROMPT = """You are a forensic smart contract security auditor.

Analyze the following Solidity source code for vulnerabilities. For each
vulnerability found, you must IMMEDIATELY verify it using the 10-step
process below. Do NOT report findings you cannot verify.

## 10-Step Verification Process (MANDATORY for each finding):
1. Ignore your own initial confidence — start from zero
2. Resolve the complete inheritance chain for all contracts involved
3. Resolve all imported files (OpenZeppelin? Custom? Missing?)
4. Find the EXACT implementation of every referenced function/modifier
5. Build the call graph (who calls what, is it reachable?)
6. Determine whether the vulnerable code path is actually reachable
7. Explain whether the code would compile (missing functions = compile error)
8. Search for code that CONTRADICTS your finding
9. Attempt to FALSIFY the finding before accepting it
10. Only include findings that survive ALL 9 steps as VERIFIED

## Output format (JSON):
{
  "findings": [
    {
      "title": "Short descriptive title",
      "severity": "Critical|High|Medium|Low|Info",
      "confidence": 0.0-1.0,
      "description": "What the vulnerability is",
      "impact": "What an attacker could do",
      "recommendation": "How to fix it",
      "line_numbers": ["42-50"],
      "poc_suggestion": "How to demonstrate the vulnerability",
      "swc_id": "SWC-XXX or empty",
      "verdict": "VERIFIED|FALSE_POSITIVE|INCONCLUSIVE",
      "evidence": "Technical evidence with exact line references and contract names",
      "inheritance_chain": "Full inheritance chain resolved",
      "call_graph": "Call graph showing reachability",
      "falsification_attempts": "What you tried to disprove this and why it failed"
    }
  ]
}

## Rules:
- ONLY include findings with verdict "VERIFIED" or "INCONCLUSIVE"
- Do NOT include "FALSE_POSITIVE" findings — discard them silently
- If source code is truncated and you can't verify, mark as INCONCLUSIVE
- Be honest: if you can't find a function's implementation, say INCONCLUSIVE
- Cite exact line numbers and contract names in evidence
- An INCONCLUSIVE finding means "I found something but can't fully verify"
- A VERIFIED finding means "I proved this is real with code evidence"

## Source code:
```solidity
{code}
```
"""


class VulnerabilityDetector:
    """AI-powered vulnerability detector + verifier (merged into one call)."""

    def __init__(self, max_code_chars: int = 12000):
        self.ai = get_ai_helper()
        self.max_code_chars = max_code_chars

    def analyze(self, source_code: str, project_name: str = "") -> list[Finding]:
        """Analyze Solidity source code — detect AND verify in one AI call.

        Returns only VERIFIED and INCONCLUSIVE findings.
        FALSE_POSITIVEs are silently discarded.
        """
        if not source_code or len(source_code.strip()) < 50:
            log.info("source too short to analyze (project=%s)", project_name)
            return []

        code = source_code[: self.max_code_chars]
        if len(source_code) > self.max_code_chars:
            log.warning(
                "source truncated from %d to %d chars (project=%s)",
                len(source_code), self.max_code_chars, project_name,
            )

        prompt = MERGED_PROMPT.replace("{code}", code)
        system = (
            "You are a forensic smart contract auditor. You find vulnerabilities "
            "AND verify them with code evidence in the same pass. You never report "
            "a finding without proving it. You actively try to FALSIFY every finding."
        )

        try:
            result = self.ai.generate_json(prompt, system)
            raw_findings = result.get("findings", [])
            findings = []

            for i, rf in enumerate(raw_findings):
                verdict = rf.get("verdict", "INCONCLUSIVE")

                # Skip FALSE_POSITIVE findings entirely
                if verdict == "FALSE_POSITIVE":
                    log.info(
                        "discarded FALSE_POSITIVE: %s",
                        rf.get("title", "Untitled")[:60],
                    )
                    continue

                finding = Finding(
                    id=f"finding-{i+1}",
                    title=rf.get("title", "Untitled"),
                    severity=rf.get("severity", "Info"),
                    confidence=float(rf.get("confidence", 0.5)),
                    description=rf.get("description", ""),
                    impact=rf.get("impact", ""),
                    recommendation=rf.get("recommendation", ""),
                    line_numbers=rf.get("line_numbers", []),
                    poc_suggestion=rf.get("poc_suggestion", ""),
                    swc_id=rf.get("swc_id", ""),
                    verdict=verdict,
                    evidence=rf.get("evidence", ""),
                    inheritance_chain=rf.get("inheritance_chain", ""),
                    call_graph=rf.get("call_graph", ""),
                    falsification_attempts=rf.get("falsification_attempts", ""),
                )
                findings.append(finding)

            verified_count = sum(1 for f in findings if f.verdict == "VERIFIED")
            inconclusive_count = sum(1 for f in findings if f.verdict == "INCONCLUSIVE")
            log.info(
                "vuln_detector: %d findings (%d VERIFIED, %d INCONCLUSIVE) for %s",
                len(findings), verified_count, inconclusive_count,
                project_name or "unknown",
            )
            return findings

        except Exception as exc:
            log.error("AI vulnerability detection failed: %s", sanitize(exc))
            return []
