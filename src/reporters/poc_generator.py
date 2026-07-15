"""
Proof of Concept (PoC) generator.

Uses AI to generate Foundry/Hardhat test cases that demonstrate
a vulnerability. The PoC is NOT auto-executed — it's a draft for
human review and local testing.
"""
from __future__ import annotations

from typing import Optional

from src.analyzers.ai_helper import get_ai_helper
from src.analyzers.vuln_detector import Finding
from src.utils.logger import get_logger
from src.utils.sanitizer import sanitize

log = get_logger("reporter.poc")


POC_PROMPT = """You are a smart contract security researcher writing a Proof of Concept (PoC)
to demonstrate a vulnerability.

Finding:
- Title: {title}
- Severity: {severity}
- Description: {description}
- Impact: {impact}

Source code:
```solidity
{code}
```

Write a Foundry test case (Solidity) that:
1. Sets up the vulnerable contract
2. Demonstrates the exploit step by step
3. Includes assertions that prove the vulnerability
4. Has clear comments explaining each step

Use this template:
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract PoC is Test {{
    // Setup
    function setUp() public {{
        // Deploy vulnerable contract
    }}

    // Exploit
    function testExploit() public {{
        // Step 1: ...
        // Step 2: ...
        // Assert: ...
    }}
}}
```

Return ONLY the Solidity code, no markdown fences.
If you cannot create a meaningful PoC from the available context,
return: "CANNOT_GENERATE_POC" and explain why briefly.
"""


class PoCGenerator:
    """Generates Foundry PoC test cases using AI."""

    def __init__(self):
        self.ai = get_ai_helper()

    def generate(self, finding: Finding, source_code: str = "") -> Optional[str]:
        """Generate a PoC for a finding.

        Returns Solidity code or None if PoC can't be generated.
        """
        code = source_code[:8000] if source_code else "(source not available)"

        prompt = POC_PROMPT.format(
            title=finding.title,
            severity=finding.severity,
            description=finding.description,
            impact=finding.impact,
            code=code,
        )

        system = "You are a smart contract exploit developer. Write minimal, clear PoCs."

        try:
            result = self.ai.generate(prompt, system)

            if "CANNOT_GENERATE_POC" in result:
                reason = result.replace("CANNOT_GENERATE_POC", "").strip()
                log.info("PoC not generated for '%s': %s", finding.title, reason[:100])
                return None

            # Strip markdown fences if present
            result = result.strip()
            if result.startswith("```"):
                lines = result.split("\n")
                lines = [ln for ln in lines if not ln.strip().startswith("```")]
                result = "\n".join(lines)

            log.info("generated PoC for: %s (%d chars)", finding.title, len(result))
            return result

        except Exception as exc:
            log.error("PoC generation failed: %s", sanitize(exc))
            return None
