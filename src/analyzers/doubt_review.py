"""
Doubt-driven adversarial review.

Uses skills/doubt-driven-development/ pattern: after the first AI pass
finds vulnerabilities, a second AI pass challenges each finding.

This is CRITICAL for bug bounty reputation:
- False positive submissions damage reputation
- Doubt review catches AI hallucinations
- Only findings that survive doubt review are submitted

Process: CLAIM → EXTRACT → DOUBT → RECONCILE → STOP
"""
from __future__ import annotations

from dataclasses import dataclass

from src.analyzers.ai_helper import get_ai_helper
from src.analyzers.vuln_detector import Finding
from src.utils.logger import get_logger

log = get_logger("doubt_review")


@dataclass
class ReviewedFinding:
    """A finding after doubt-driven review."""
    original: Finding
    survives: bool  # True if the finding is likely valid after review
    confidence_adjusted: float
    doubts: str
    recommendation: str  # "submit" | "investigate" | "discard"

    def to_dict(self) -> dict:
        return {
            "original": self.original.to_dict(),
            "survives": self.survives,
            "confidence_adjusted": self.confidence_adjusted,
            "doubts": self.doubts,
            "recommendation": self.recommendation,
        }


DOUBT_PROMPT = """You are a skeptical senior security reviewer. Another auditor found
this potential vulnerability. Your job is to doubt it — find every reason
it might be wrong.

For each finding, ask:
1. Is this actually a vulnerability, or is it a known safe pattern?
2. Are there mitigating factors the first auditor missed?
3. Is the impact overstated?
4. Is the confidence level too high?
5. Could this be a false positive due to truncated code context?

Be brutally honest. It's better to discard a weak finding than to submit
a false positive and damage reputation.

Finding to review:
- Title: {title}
- Severity: {severity}
- Confidence: {confidence}
- Description: {description}
- Impact: {impact}
- SWC ID: {swc_id}

Source code context:
```solidity
{code}
```

Return JSON:
{{
  "survives": true/false,
  "confidence_adjusted": 0.0-1.0,
  "doubts": "what concerns you about this finding",
  "recommendation": "submit" | "investigate" | "discard"
}}
"""


class DoubtReviewer:
    """Adversarial reviewer that challenges findings."""

    def __init__(self, max_code_chars: int = 15000):
        self.ai = get_ai_helper()
        self.max_code_chars = max_code_chars

    def review(
        self,
        finding: Finding,
        source_code: str = "",
    ) -> ReviewedFinding:
        """Review a single finding with adversarial analysis."""
        code = source_code[: self.max_code_chars] if source_code else "(source not available)"

        prompt = DOUBT_PROMPT.format(
            title=finding.title,
            severity=finding.severity,
            confidence=finding.confidence,
            description=finding.description,
            impact=finding.impact,
            swc_id=finding.swc_id or "N/A",
            code=code,
        )

        system = (
            "You are a skeptical security reviewer. Your job is to find "
            "flaws in the auditor's reasoning, not to confirm it."
        )

        try:
            result = self.ai.generate_json(prompt, system)
            survives = result.get("survives", False)
            confidence_adj = float(result.get("confidence_adjusted", finding.confidence * 0.5))

            # Determine recommendation
            recommendation = result.get("recommendation", "discard")
            if recommendation not in ("submit", "investigate", "discard"):
                if survives and confidence_adj >= 0.7:
                    recommendation = "submit"
                elif survives:
                    recommendation = "investigate"
                else:
                    recommendation = "discard"

            return ReviewedFinding(
                original=finding,
                survives=survives,
                confidence_adjusted=confidence_adj,
                doubts=result.get("doubts", ""),
                recommendation=recommendation,
            )
        except Exception as exc:
            log.error("doubt review failed: %s", exc)
            # On error, be conservative — don't submit
            return ReviewedFinding(
                original=finding,
                survives=False,
                confidence_adjusted=0.0,
                doubts=f"Review failed: {exc}",
                recommendation="discard",
            )

    def review_many(
        self,
        findings: list[Finding],
        source_code: str = "",
    ) -> list[ReviewedFinding]:
        """Review multiple findings. Returns ReviewedFinding list."""
        results = []
        for finding in findings:
            reviewed = self.review(finding, source_code)
            results.append(reviewed)
            log.info(
                "doubt_review: '%s' -> survives=%s recommend=%s",
                finding.title, reviewed.survives, reviewed.recommendation,
            )
        return results

    def filter_submittable(self, reviewed: list[ReviewedFinding]) -> list[ReviewedFinding]:
        """Return only findings recommended for submission."""
        return [r for r in reviewed if r.recommendation == "submit"]
