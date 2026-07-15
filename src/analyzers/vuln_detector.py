"""
AI-powered vulnerability detector.

Analyzes Solidity source code using AI (Gemini/Groq) to find
vulnerabilities. Returns structured findings with severity,
impact, and PoC suggestion.

The prompt is based on the SWC (Smart Contract Weakness Classification)
Registry and common Web3 vulnerability patterns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.analyzers.ai_helper import get_ai_helper
from src.utils.logger import get_logger

log = get_logger("vuln_detector")


@dataclass
class Finding:
    """A vulnerability finding."""
    id: str
    title: str
    severity: str  # Critical | High | Medium | Low | Info
    confidence: float  # 0.0 to 1.0
    description: str
    impact: str
    recommendation: str
    line_numbers: list[str] = field(default_factory=list)
    poc_suggestion: str = ""
    swc_id: str = ""  # SWC registry ID if applicable

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
        }


# AI prompt template for vulnerability detection
VULN_DETECTION_PROMPT = """You are an expert smart contract security auditor specializing in Solidity.
Analyze the following Solidity source code for vulnerabilities.

For each vulnerability found, provide:
1. Title (short, descriptive)
2. Severity (Critical, High, Medium, Low, or Info)
3. Confidence (0.0 to 1.0 — how sure are you this is a real vulnerability?)
4. Description (what the vulnerability is)
5. Impact (what an attacker could do)
6. Recommendation (how to fix it)
7. Line numbers (if identifiable)
8. PoC suggestion (brief description of how to demonstrate the vulnerability)
9. SWC ID (if applicable, from https://swcregistry.io/)

Focus on these vulnerability categories:
- Reentrancy (SWC-107)
- Integer overflow/underflow (SWC-101)
- Unchecked external calls (SWC-104)
- Access control issues (SWC-105)
- tx.origin authentication (SWC-115)
- Delegatecall to untrusted callee (SWC-112)
- Uninitialized storage pointers (SWC-109)
- Arbitrary jump with function type variable (SWC-127)
- DoS with block gas limit (SWC-128)
- DoS with unexpected revert (SWC-113)
- Oracle manipulation
- Flash loan attacks
- Front-running
- Timestamp dependence (SWC-116)
- Inconsistent state checks

Only report REAL vulnerabilities. Do not report style issues or gas optimizations.

Return your response as JSON with this exact format:
{
  "findings": [
    {
      "title": "...",
      "severity": "Medium",
      "confidence": 0.8,
      "description": "...",
      "impact": "...",
      "recommendation": "...",
      "line_numbers": ["42-50"],
      "poc_suggestion": "...",
      "swc_id": "SWC-107"
    }
  ]
}

If no vulnerabilities are found, return: {"findings": []}

Source code to analyze:
```solidity
{code}
```
"""


class VulnerabilityDetector:
    """AI-powered vulnerability detector."""

    def __init__(self, max_code_chars: int = 30000):
        self.ai = get_ai_helper()
        self.max_code_chars = max_code_chars

    def analyze(self, source_code: str, project_name: str = "") -> list[Finding]:
        """Analyze Solidity source code for vulnerabilities.

        Args:
            source_code: Solidity source code
            project_name: Project name for context

        Returns:
            List of Finding objects
        """
        if not source_code or len(source_code.strip()) < 50:
            log.info("source too short to analyze (project=%s)", project_name)
            return []

        # Truncate if too long (AI context limit)
        code = source_code[: self.max_code_chars]
        if len(source_code) > self.max_code_chars:
            log.warning(
                "source truncated from %d to %d chars (project=%s)",
                len(source_code), self.max_code_chars, project_name,
            )

        prompt = VULN_DETECTION_PROMPT.replace("{code}", code)
        system = "You are a senior smart contract security auditor with 10+ years of experience."

        try:
            result = self.ai.generate_json(prompt, system)
            raw_findings = result.get("findings", [])
            findings = []

            for i, rf in enumerate(raw_findings):
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
                )
                findings.append(finding)

            log.info(
                "vuln_detector: found %d findings for %s",
                len(findings), project_name or "unknown project",
            )
            return findings

        except Exception as exc:
            log.error("AI vulnerability detection failed: %s", exc)
            return []
