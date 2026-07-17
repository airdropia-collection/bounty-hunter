"""
Vulnerability report drafter.

Generates formal bug bounty reports using AI, formatted per platform
(Immunefi, Code4rana, Sherlock). Each platform has different report
requirements — this module handles the templates.
"""
from __future__ import annotations

from src.analyzers.ai_helper import get_ai_helper
from src.analyzers.vuln_detector import Finding
from src.utils.logger import get_logger
from src.utils.sanitizer import sanitize

log = get_logger("reporter.drafter")


# AI prompt for report drafting
REPORT_DRAFT_PROMPT = """You are writing a formal bug bounty vulnerability report.
The report must be professional, clear, and include all information a
bug bounty triager needs to validate the finding.

Finding details:
- Title: {title}
- Severity: {severity}
- Confidence: {confidence}
- Description: {description}
- Impact: {impact}
- Recommendation: {recommendation}
- SWC ID: {swc_id}

Source code context:
```
{code}
```

Write a formal report with these sections:
1. **Summary** — one paragraph overview
2. **Vulnerability Detail** — technical explanation with code references
3. **Impact** — what an attacker can do, realistic scenario
4. **Proof of Concept** — step-by-step how to reproduce (or code snippet)
5. **Recommendation** — specific fix with code example
6. **References** — SWC registry, related CVEs, blog posts

Return the report as Markdown. Be concise but complete.
Do not include false confidence — if unsure, say "likely" or "may".
"""


class ReportDrafter:
    """Drafts formal vulnerability reports using AI."""

    def __init__(self):
        self.ai = get_ai_helper()

    def draft(
        self,
        finding: Finding,
        source_code: str = "",
        platform: str = "",
        bounty_url: str = "",
    ) -> str:
        """Draft a formal vulnerability report.

        Args:
            finding: The Finding object from vuln_detector
            source_code: Source code for context (truncated)
            platform: Target platform (immunefi/code4rana/sherlock)
            bounty_url: URL of the bounty listing

        Returns:
            Markdown report string
        """
        code = source_code[:5000] if source_code else "(source not available)"

        prompt = REPORT_DRAFT_PROMPT.format(
            title=finding.title,
            severity=finding.severity,
            confidence=finding.confidence,
            description=finding.description,
            impact=finding.impact,
            recommendation=finding.recommendation,
            swc_id=finding.swc_id or "N/A",
            code=code,
        )

        system = (
            "You are a professional smart contract security researcher "
            "writing a bug bounty report. Be precise, technical, and honest."
        )

        try:
            report = self.ai.generate(prompt, system)

            # Add header with metadata
            header = f"## Vulnerability Report: {finding.title}\n\n"
            header += f"**Platform:** {platform}\n"
            header += f"**Bounty URL:** {bounty_url}\n"
            header += f"**Severity:** {finding.severity}\n"
            header += f"**Confidence:** {finding.confidence:.0%}\n"
            if finding.swc_id:
                header += f"**SWC ID:** {finding.swc_id}\n"
            header += "**Report Generated:** AI-drafted (needs human review)\n\n"
            header += "---\n\n"

            log.info("drafted report for: %s", finding.title)
            return header + report

        except Exception as exc:
            log.error("report drafting failed: %s", sanitize(exc))
            # Return a minimal report on failure
            return (
                f"## Vulnerability Report: {finding.title}\n\n"
                f"**Error:** AI report generation failed.\n"
                f"**Finding:** {finding.description}\n"
                f"**Severity:** {finding.severity}\n"
                f"**Manual report needed.**\n"
            )
