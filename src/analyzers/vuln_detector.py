"""
AI-powered vulnerability detector + verifier (multi-language, merged).

Single AI call that:
1. Detects vulnerabilities in source code (any language)
2. Immediately verifies each finding with the 10-step process
3. Returns only VERIFIED findings (FALSE_POSITIVEs are discarded)

Language-aware prompts:
- Solidity: smart contract audit (reentrancy, overflow, access control, etc.)
- JavaScript/TypeScript: XSS, prototype pollution, SSRF, injection, etc.
- Python: SQL injection, deserialization, path traversal, etc.
- Java: SSRF, deserialization, XXE, etc.
- Go: race conditions, command injection, etc.
- Other languages: generic security review

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
    evidence: str = ""
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


# --------------------------------------------------------------------------- #
# Language-specific prompt templates
# --------------------------------------------------------------------------- #
PROMPT_HEADER = """You are a forensic security auditor.

Analyze the following source code for vulnerabilities. For each vulnerability
found, you must IMMEDIATELY verify it using the 10-step process below. Do NOT
report findings you cannot verify.

## 10-Step Verification Process (MANDATORY for each finding):
1. Ignore your own initial confidence — start from zero
2. Resolve the complete inheritance/dependency chain for all modules involved
3. Resolve all imported files (third-party libs? Custom? Missing?)
4. Find the EXACT implementation of every referenced function/method
5. Build the call graph (who calls what, is it reachable?)
6. Determine whether the vulnerable code path is actually reachable
7. Explain whether the code would compile/run (missing functions = error)
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
      "swc_id": "SWC-XXX or CVE-XXX or empty",
      "verdict": "VERIFIED|FALSE_POSITIVE|INCONCLUSIVE",
      "evidence": "Technical evidence with exact line references and function names",
      "inheritance_chain": "Full dependency chain resolved",
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
- Cite exact line numbers and function/class names in evidence
- An INCONCLUSIVE finding means "I found something but can't fully verify"
- A VERIFIED finding means "I proved this is real with code evidence"

## Source code:
"""

PROMPT_FOOTER = """
```
"""


# Language-specific vulnerability checklists (appended to prompt header)
LANGUAGE_CHECKLISTS: dict[str, str] = {
    "solidity": """
## Vulnerability checklist (Solidity):
- Reentrancy (external calls before state updates)
- Integer overflow/underflow (pre-0.8.0 or unchecked blocks)
- Access control (missing onlyOwner, wrong modifier)
- Unchecked external calls (call.send, transfer)
- Front-running (MEV, sandwich attacks)
- Timestamp dependence (block.timestamp manipulation)
- Tx.origin authentication
- Delegatecall to untrusted contracts
- Self-destruct abuse
- Randomness from block variables
- Gas limit DoS (unbounded loops)
- Storage collisions (proxy patterns)
- Flash loan attacks
- Oracle manipulation
- Privilege escalation
```solidity
""",
    "javascript": """
## Vulnerability checklist (JavaScript/Node.js):
- XSS: innerHTML, dangerouslySetInnerHTML, eval, document.write
- Prototype pollution (Object.assign, merge, lodash.set)
- SQL injection (string concatenation in queries)
- NoSQL injection (MongoDB $where, $gt)
- SSRF (unvalidated URL fetch)
- Path traversal (../ in file paths, path.join user input)
- Command injection (exec, spawn with user input)
- Insecure deserialization (JSON.parse of untrusted data)
- Hardcoded secrets/credentials
- Insecure crypto (Math.random, MD5, weak HMAC)
- Open redirect (unvalidated URL in redirect)
- CSRF (missing tokens, SameSite issues)
- Prototype access (obj['__proto__'], constructor pollution)
- Regex DoS (catastrophic backtracking)
- Regex injection (user-controlled patterns)
- Eval of user input (eval, Function, vm.runInNewContext)
```javascript
""",
    "typescript": """
## Vulnerability checklist (TypeScript):
- All JavaScript issues apply (TS compiles to JS)
- Type assertion bypass (as any, ts-ignore hiding bugs)
- Unsafe type casts (unknown → specific without validation)
- Decorator misuse (mutating class metadata insecurely)
- Enum reverse mapping leaks (numeric enum → string)
- Generic constraint bypass
```typescript
""",
    "python": """
## Vulnerability checklist (Python):
- SQL injection (f-strings, .format, % in queries)
- Command injection (os.system, subprocess with shell=True)
- Pickle/yaml.load deserialization (RCE)
- Path traversal (open() with user input, os.path.join)
- SSRF (requests/urllib with user URL)
- XXE (lxml, xml.etree without defusedxml)
- Eval/exec of user input
- Template injection (Jinja2, Mako with user input)
- Hardcoded secrets
- Weak crypto (hashlib.md5, random instead of secrets)
- SSRF via redirect chains
- Regex DoS (catastrophic backtracking)
- Race conditions (TOCTOU in file ops)
- Code injection via ast.literal_eval on non-literals
```python
""",
    "java": """
## Vulnerability checklist (Java):
- SQL injection (Statement, string concat in queries)
- SSRF (URLConnection, HttpClient with user URL)
- Deserialization (ObjectInputStream, Jackson polymorphic)
- XXE (DocumentBuilder, SAXParser without disabling external entities)
- Path traversal (File with user input)
- Command injection (Runtime.exec, ProcessBuilder)
- SpEL injection (Spring Expression Language)
- JNDI injection (log4shell-style)
- LDAP injection
- XPath injection
- Open redirect
- Hardcoded secrets
- Weak crypto (DES, MD5)
- Race conditions (synchronized misuse)
```java
""",
    "go": """
## Vulnerability checklist (Go):
- SQL injection (database/sql with string concat)
- Command injection (os/exec with user input)
- Path traversal (filepath.Join, os.Open with user input)
- SSRF (http.Get/Post with user URL)
- Insecure crypto (math/rand for security, weak hashing)
- Race conditions (shared state without sync)
- Goroutine leaks (uncancelled contexts)
- Hardcoded secrets
- Template injection (text/template with user input)
- Regex DoS (catastrophic backtracking)
```go
""",
    "rust": """
## Vulnerability checklist (Rust):
- Unsafe blocks (raw pointer dereference, FFI)
- Logic bugs in unsafe code
- Memory issues in unsafe (use-after-free, double free)
- Race conditions (unsafe concurrent access)
- Command injection (std::process::Command with user input)
- SQL injection (string concat in queries)
- Path traversal (std::fs with user input)
- Hardcoded secrets
- Weak crypto (custom implementations)
```rust
""",
    "csharp": """
## Vulnerability checklist (C#/.NET):
- SQL injection (SqlCommand with string concat)
- Command injection (Process.Start with user input)
- Path traversal (File.Open with user input)
- XXE (XmlDocument without disabling DTD)
- Deserialization (BinaryFormatter, TypeNameHandling)
- SSRF (HttpClient with user URL)
- XPath injection
- Regex injection
- Open redirect
- Hardcoded secrets
- Weak crypto (MD5, DES)
- ViewState tampering (unencrypted MAC)
```csharp
""",
    "ruby": """
## Vulnerability checklist (Ruby):
- SQL injection (string interpolation in queries)
- Command injection (backticks, system, exec with user input)
- SSRF (Net::HTTP, open-uri with user URL)
- Path traversal (File.join, File.open with user input)
- Deserialization (Marshal.load, YAML.load)
- ERB injection (user input in templates)
- eval of user input
- Hardcoded secrets
- Weak crypto (MD5, custom implementations)
- Regex DoS
```ruby
""",
    "php": """
## Vulnerability checklist (PHP):
- SQL injection (mysql_query, mysqli with string concat)
- XSS (echo, print of user input without htmlspecialchars)
- Command injection (exec, system, shell_exec, backticks)
- File inclusion (include, require with user input → LFI/RFI)
- Path traversal (fopen, file_get_contents with user input)
- SSRF (curl, file_get_contents with user URL)
- Deserialization (unserialize of user input)
- eval of user input
- preg_replace /e modifier (RCE)
- Hardcoded secrets
- Weak crypto (md5, sha1)
- Session fixation
- Open redirect
```php
""",
    "swift": """
## Vulnerability checklist (Swift/iOS):
- Force unwrapping of nil optionals (crash)
- Improper keychain usage (kSecAttrAccessible default)
- Insecure storage (UserDefaults for secrets)
- TLS validation bypass (URLSession delegate)
- Hardcoded secrets in code/bundles
- Weak crypto (CommonCrypto MD5)
- Path traversal (FileManager with user input)
- WebView JavaScript injection (evaluateJavaScript with user input)
- App transport security disabled
```swift
""",
    "kotlin": """
## Vulnerability checklist (Kotlin/Android):
- All Java issues apply
- Force unwrapping (!! operator → crash)
- Improper fragment argument validation
- Intent redirection (user-controlled PendingIntent)
- WebView JavaScript interface exposure
- Hardcoded secrets
- Insecure TLS
- SQLite injection (rawQuery with user input)
```kotlin
""",
}

# Generic checklist for languages without specific checklist
GENERIC_CHECKLIST = """
## Vulnerability checklist (general software security):
- Input validation issues (missing sanitization)
- Authentication/authorization bypass
- Injection attacks (SQL, command, LDAP, XPath)
- Path traversal
- SSRF (server-side request forgery)
- Insecure deserialization
- Hardcoded secrets/credentials
- Weak cryptography
- Race conditions
- Error handling that leaks info
- Improper resource management (memory, file handles)
- Logic bugs leading to security impact
```
"""

# Languages that get the generic checklist
GENERIC_LANGUAGES = {
    "c", "cpp", "objc", "scala", "clojure", "haskell", "elixir", "erlang",
    "ocaml", "fsharp", "shell", "powershell", "dart", "julia", "r", "nim",
    "crystal", "zig", "vue", "svelte", "lua", "perl", "ruby",  # ruby has specific
}


def _build_prompt(source_code: str, language: str | None = None) -> str:
    """Build a language-aware prompt for the AI."""
    checklist = LANGUAGE_CHECKLISTS.get(language or "", GENERIC_CHECKLIST)
    if not checklist and language in GENERIC_LANGUAGES:
        checklist = GENERIC_CHECKLIST
    elif not checklist:
        checklist = GENERIC_CHECKLIST

    return PROMPT_HEADER + checklist + f"\n{source_code}\n" + PROMPT_FOOTER


def _get_system_prompt(language: str | None = None) -> str:
    """Get the system prompt — language-aware."""
    if language == "solidity":
        return (
            "You are a forensic smart contract auditor. You find vulnerabilities "
            "AND verify them with code evidence in the same pass. You never report "
            "a finding without proving it. You actively try to FALSIFY every finding."
        )
    return (
        "You are a forensic security auditor specializing in "
        f"{language or 'general software'} code. You find vulnerabilities "
        "AND verify them with code evidence in the same pass. You never report "
        "a finding without proving it. You actively try to FALSIFY every finding. "
        "You focus on real, exploitable security issues — not style or best practices."
    )


class VulnerabilityDetector:
    """AI-powered vulnerability detector + verifier (multi-language, merged)."""

    def __init__(self, max_code_chars: int = 12000):
        self.ai = get_ai_helper()
        self.max_code_chars = max_code_chars

    def analyze(
        self,
        source_code: str,
        project_name: str = "",
        language: str | None = None,
    ) -> list[Finding]:
        """Analyze source code — detect AND verify in one AI call.

        Args:
            source_code: The source code to analyze
            project_name: Project name for logging
            language: Programming language ("solidity", "python", "javascript", etc.)
                      If None, uses generic security review prompt

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

        prompt = _build_prompt(code, language)
        system = _get_system_prompt(language)

        log.info(
            "analyzing %s as %s (%d chars)",
            project_name or "unknown",
            language or "generic",
            len(code),
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
                "vuln_detector: %d findings (%d VERIFIED, %d INCONCLUSIVE) for %s [%s]",
                len(findings), verified_count, inconclusive_count,
                project_name or "unknown", language or "generic",
            )
            return findings

        except Exception as exc:
            log.error("AI vulnerability detection failed: %s", sanitize(exc))
            return []
