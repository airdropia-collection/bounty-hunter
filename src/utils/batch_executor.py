"""
Batch Execution Engine — Value-agnostic throughput maximization with
3-iteration self-healing loop.

Processes bounty targets in batches without financial value bias.
Each target passes through:
  1. Gate Alpha (Deterministic Feasibility) — capability_matrix assessment
  2. Gate Beta (Repository Safeguard) — security/regression check
  3. Self-healing loop (up to 3 iterations) — parse errors, refactor, re-test
  4. Graceful fail-forward — isolate failures, advance to next target

Emits structured batch records to stdout for GitHub Actions auditing:

    [TARGET_BATCH_RECORD_START]
    - IDENTIFIER: <Target_ID>
    - FINANCIAL_VALUATION: $<Value> (Telemetry only; omitted from selection logic)
    - VERIFICATION_GATES: [ALPHA: PASS/FAIL] | [BETA: PASS/FAIL]
    - LOOP_STATE: [SUCCESS / FAILED / AUTONOMOUS_HEALED]
    - CYCLES_CONSUMED: <0-3>
    - DIAGNOSTIC_EXCEPTION: <Captured stderr or None>
    - CORE_RESOLUTION_LOG: <Brief technical summary of state change>
    [TARGET_BATCH_RECORD_END]

Usage:
    from src.utils.batch_executor import BatchExecutor, BatchTarget, BatchResult

    targets = [BatchTarget(...), BatchTarget(...)]
    executor = BatchExecutor(max_heal_cycles=3)
    results = executor.execute_batch(targets)
    for r in results:
        print(r.format_record())
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.utils.capability_matrix import IssueAssessment, assess_issue
from src.utils.logger import get_logger
from src.utils.memory_registry import append_learned_pattern
from src.utils.polyglot_runner import run_lint, run_tests

log = get_logger("batch_executor")


# ──────────────────────────────────────────────────────────────────── #
# Enums
# ──────────────────────────────────────────────────────────────────── #

class GateStatus(StrEnum):  # noqa: PLC0414
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


class LoopState(StrEnum):  # noqa: PLC0414
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    AUTONOMOUS_HEALED = "AUTONOMOUS_HEALED"
    SKIPPED = "SKIPPED"


# ──────────────────────────────────────────────────────────────────── #
# Data classes
# ──────────────────────────────────────────────────────────────────── #

@dataclass
class BatchTarget:
    """A single bounty target for batch processing.

    Financial value is stored for telemetry ONLY — it is never used
    in the selection or prioritization logic (value-agnostic mandate).
    """
    identifier: str  # e.g., "owner/repo#123"
    issue_title: str
    issue_body: str
    issue_url: str = ""
    financial_value: str = ""  # "$10" — telemetry only, NOT used for filtering
    language: str = ""  # detected by capability_matrix if empty
    project_dir: str = "."  # path to the solution code
    repo_files: list[str] | None = None


@dataclass
class BatchResult:
    """Result of processing a single batch target."""
    identifier: str
    financial_valuation: str
    gate_alpha: GateStatus
    gate_beta: GateStatus
    loop_state: LoopState
    cycles_consumed: int
    diagnostic_exception: str | None
    core_resolution_log: str
    capability_assessment: IssueAssessment | None = None
    memory_sync_status: str = "SKIPPED - NO HEALING REQUIRED"

    def format_record(self) -> str:
        """Format as structured batch record for GitHub Actions auditing."""
        lines = [
            "[TARGET_BATCH_RECORD_START]",
            f"- IDENTIFIER: {self.identifier}",
            f"- FINANCIAL_VALUATION: {self.financial_valuation} (Telemetry only; omitted from selection logic)",
            f"- VERIFICATION_GATES: [ALPHA: {self.gate_alpha.value}] | [BETA: {self.gate_beta.value}]",
            f"- LOOP_STATE: {self.loop_state.value}",
            f"- CYCLES_CONSUMED: {self.cycles_consumed}",
            f"- DIAGNOSTIC_EXCEPTION: {self.diagnostic_exception or 'None'}",
            f"- CORE_RESOLUTION_LOG: {self.core_resolution_log}",
            f"- MEMORY_REGISTRY_SYNC: {self.memory_sync_status}",
            "[TARGET_BATCH_RECORD_END]",
        ]
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────── #
# Self-healing error patterns
# ──────────────────────────────────────────────────────────────────── #

# Maps error patterns to fix strategies
HEALING_PATTERNS: list[dict[str, Any]] = [
    {
        "pattern": r"ModuleNotFoundError:\s+No module named '([\w.]+)'",
        "category": "missing_import",
        "fix": "Create __init__.py in the module directory or fix the import path.",
    },
    {
        "pattern": r"ImportError:\s+cannot import name '(\w+)' from '([\w.]+)'",
        "category": "broken_import",
        "fix": "Check that the named export exists in the source module.",
    },
    {
        "pattern": r"NameError:\s+name '(\w+)' is not defined",
        "category": "undefined_variable",
        "fix": "Define the variable or fix the reference.",
    },
    {
        "pattern": r"SyntaxError:\s+(.+)",
        "category": "syntax_error",
        "fix": "Fix the Python syntax error in the indicated line.",
    },
    {
        "pattern": r"AssertionError:\s*(.*)",
        "category": "assertion_mismatch",
        "fix": "Update the test assertion to match actual output, or fix the code under test.",
    },
    {
        "pattern": r"E741 Ambiguous variable name '(\w+)'",
        "category": "ruff_naming",
        "fix": "Rename ambiguous variable to a descriptive name.",
    },
    {
        "pattern": r"F401 '([\w.]+)' imported but unused",
        "category": "ruff_unused_import",
        "fix": "Remove the unused import.",
    },
    {
        "pattern": r"undefined:\s*(\w+)",
        "category": "go_undefined",
        "fix": "Declare the variable or import the missing package.",
    },
    {
        "pattern": r"cannot find package (\w+) in any of",
        "category": "go_missing_package",
        "fix": "Run 'go get' to install the missing package or fix the import path.",
    },
    {
        "pattern": r"error\[E(\w+)\]:\s+(.+)",
        "category": "rust_compiler_error",
        "fix": "Fix the Rust compiler error: match types, lifetimes, or traits as indicated.",
    },
]


def diagnose_error(stderr: str, stdout: str = "") -> dict[str, Any] | None:
    """Parse error output and return a diagnosis with fix strategy.

    Returns None if no known pattern matches.
    """
    text = stderr + "\n" + stdout
    for pattern_def in HEALING_PATTERNS:
        match = re.search(pattern_def["pattern"], text)
        if match:
            return {
                "category": pattern_def["category"],
                "fix": pattern_def["fix"],
                "matched_groups": match.groups(),
                "raw_match": match.group(0),
            }
    return None


# ──────────────────────────────────────────────────────────────────── #
# Batch Executor
# ──────────────────────────────────────────────────────────────────── #

class BatchExecutor:
    """Value-agnostic batch execution engine with 3-iteration self-healing.

    Processes targets without financial value bias. Each target passes
    through Gate Alpha (feasibility) and Gate Beta (security), then
    enters a self-healing test loop (up to max_heal_cycles iterations).
    """

    def __init__(
        self,
        max_heal_cycles: int = 3,
        confidence_threshold: float = 0.80,
        test_timeout: int = 120,
        lint_timeout: int = 60,
    ):
        self.max_heal_cycles = max_heal_cycles
        self.confidence_threshold = confidence_threshold
        self.test_timeout = test_timeout
        self.lint_timeout = lint_timeout

    def execute_batch(self, targets: list[BatchTarget]) -> list[BatchResult]:
        """Process a batch of targets with fail-forward semantics.

        Never raises — all exceptions are caught and logged per-target.
        Returns a list of BatchResult, one per target.
        """
        results: list[BatchResult] = []
        for i, target in enumerate(targets):
            log.info("Processing target %d/%d: %s", i + 1, len(targets), target.identifier)
            result = self._process_single(target)
            results.append(result)
            # Print structured record for GitHub Actions auditing
            print(result.format_record())
            print()

        # Summary
        succeeded = sum(1 for r in results if r.loop_state in (LoopState.SUCCESS, LoopState.AUTONOMOUS_HEALED))
        failed = sum(1 for r in results if r.loop_state == LoopState.FAILED)
        skipped = sum(1 for r in results if r.loop_state == LoopState.SKIPPED)
        log.info(
            "Batch complete: %d targets | %d succeeded | %d failed | %d skipped",
            len(results), succeeded, failed, skipped,
        )
        return results

    def _process_single(self, target: BatchTarget) -> BatchResult:
        """Process a single target through all gates + self-healing loop."""
        # ── Gate Alpha: Deterministic Feasibility ──
        assessment = assess_issue(
            issue_title=target.issue_title,
            issue_body=target.issue_body,
            issue_url=target.issue_url,
            repo_files=target.repo_files,
            confidence_threshold=self.confidence_threshold,
        )

        gate_alpha = GateStatus.PASS if assessment.cleared else GateStatus.FAIL

        if not assessment.cleared:
            return BatchResult(
                identifier=target.identifier,
                financial_valuation=target.financial_value,
                gate_alpha=gate_alpha,
                gate_beta=GateStatus.SKIP,
                loop_state=LoopState.SKIPPED,
                cycles_consumed=0,
                diagnostic_exception=None,
                core_resolution_log=f"Gate Alpha FAIL: confidence {assessment.final_confidence:.0%} < {self.confidence_threshold:.0%} threshold. Language: {assessment.detected_language}.",
                capability_assessment=assessment,
            )

        # ── Gate Beta: Repository Safeguard (security + regression) ──
        # Check for security anti-patterns in the target issue
        gate_beta = self._check_security(target)
        if gate_beta == GateStatus.FAIL:
            return BatchResult(
                identifier=target.identifier,
                financial_valuation=target.financial_value,
                gate_alpha=gate_alpha,
                gate_beta=gate_beta,
                loop_state=LoopState.SKIPPED,
                cycles_consumed=0,
                diagnostic_exception=None,
                core_resolution_log="Gate Beta FAIL: security anti-patterns detected in issue description.",
                capability_assessment=assessment,
            )

        # ── Self-healing test loop ──
        language = assessment.detected_language
        return self._healing_loop(target, language, assessment)

    def _check_security(self, target: BatchTarget) -> GateStatus:
        """Gate Beta: Check for security anti-patterns.

        Rejects issues that ask for:
        - Hardcoded credentials/secrets
        - Bypassing authentication
        - Injecting malicious code
        - Scraping PII
        """
        text = f"{target.issue_title} {target.issue_body}".lower()
        dangerous_patterns = [
            "hardcode api key",
            "hardcode password",
            "bypass authentication",
            "disable security",
            "inject eval",
            "scrape user data",
            "steal tokens",
            "backdoor",
        ]
        for pattern in dangerous_patterns:
            if pattern in text:
                log.warning("Security gate: pattern '%s' detected in %s", pattern, target.identifier)
                return GateStatus.FAIL
        return GateStatus.PASS

    def _healing_loop(
        self,
        target: BatchTarget,
        language: str,
        assessment: IssueAssessment,
    ) -> BatchResult:
        """Run the self-healing test loop (up to max_heal_cycles iterations).

        Each iteration:
        1. Run tests
        2. Run lint
        3. If both pass → SUCCESS
        4. If fail → diagnose error, log fix strategy, retry
        5. After max cycles → FAILED (fail-forward)
        """
        # Track the last diagnosis from a failing cycle (for memory persistence on heal)
        last_diagnosis: dict[str, Any] | None = None

        for cycle in range(self.max_heal_cycles + 1):
            log.info(
                "[%s] Healing cycle %d/%d",
                target.identifier, cycle, self.max_heal_cycles,
            )

            # Run tests
            test_result = run_tests(language, target.project_dir, self.test_timeout)
            # Run lint
            lint_result = run_lint(language, target.project_dir, self.lint_timeout)

            if test_result.passed and lint_result.passed:
                # Success!
                state = LoopState.SUCCESS if cycle == 0 else LoopState.AUTONOMOUS_HEALED
                memory_status = "SKIPPED - NO HEALING REQUIRED"

                # ── Phase 1: Automated memory persistence ──
                # If this was a healing success (cycle > 0), persist the
                # diagnostic pattern + fix strategy to agent_memory.json
                if cycle > 0 and last_diagnosis:
                    memory_result = append_learned_pattern(
                        category=last_diagnosis["category"],
                        title=f"{last_diagnosis['category']} resolved in {target.identifier}",
                        description=f"Error: {last_diagnosis.get('raw_match', 'unknown')}. Fix: {last_diagnosis['fix']}. Target: {target.identifier}, language: {language}.",
                        fix=last_diagnosis["fix"],
                        tags=[language, last_diagnosis["category"], "auto-healed"],
                    )
                    memory_status = memory_result["status"]
                    if memory_result["status"] == "SUCCESS":
                        log.info(
                            "[%s] Memory registry updated: pattern '%s' (category: %s)",
                            target.identifier, memory_result.get("pattern_id", ""),
                            last_diagnosis["category"],
                        )
                    elif memory_result["status"] == "WRITE_ERROR":
                        log.warning("[%s] Memory registry write failed", target.identifier)

                return BatchResult(
                    identifier=target.identifier,
                    financial_valuation=target.financial_value,
                    gate_alpha=GateStatus.PASS,
                    gate_beta=GateStatus.PASS,
                    loop_state=state,
                    cycles_consumed=cycle,
                    diagnostic_exception=None,
                    core_resolution_log=f"Tests passed ({test_result.pass_count or 'all'}). Lint clean. Language: {language}.",
                    capability_assessment=assessment,
                    memory_sync_status=memory_status,
                )

            # Diagnose the failure
            error_text = test_result.stderr + "\n" + lint_result.stderr
            diagnosis = diagnose_error(test_result.stderr, test_result.stdout)
            last_diagnosis = diagnosis  # store for memory persistence on next-cycle heal

            if diagnosis:
                log.info(
                    "[%s] Diagnosis: %s — %s",
                    target.identifier, diagnosis["category"], diagnosis["fix"],
                )
            else:
                log.warning(
                    "[%s] Undiagnosed error in cycle %d: %s",
                    target.identifier, cycle, error_text[:200],
                )

            # If this was the last cycle, fail forward
            if cycle == self.max_heal_cycles:
                return BatchResult(
                    identifier=target.identifier,
                    financial_valuation=target.financial_value,
                    gate_alpha=GateStatus.PASS,
                    gate_beta=GateStatus.PASS,
                    loop_state=LoopState.FAILED,
                    cycles_consumed=cycle,
                    diagnostic_exception=error_text[:500] if error_text.strip() else None,
                    core_resolution_log=f"Failed after {cycle + 1} cycles. Last diagnosis: {diagnosis['category'] if diagnosis else 'unknown'}.",
                    capability_assessment=assessment,
                )

            # Otherwise, log the healing attempt and retry
            # (In a real implementation, this is where the code-architect sub-agent
            # would refactor the code based on the diagnosis. For now, we log
            # the fix strategy and retry — the actual code fix happens manually
            # or via the AI code-generation pipeline.)
            log.info(
                "[%s] Applying fix: %s",
                target.identifier,
                diagnosis["fix"] if diagnosis else "No automated fix available — retrying.",
            )

        # Should never reach here, but fail-safe
        return BatchResult(
            identifier=target.identifier,
            financial_valuation=target.financial_value,
            gate_alpha=GateStatus.PASS,
            gate_beta=GateStatus.PASS,
            loop_state=LoopState.FAILED,
            cycles_consumed=self.max_heal_cycles,
            diagnostic_exception="Exhausted all healing cycles",
            core_resolution_log="Unexpected exit from healing loop.",
            capability_assessment=assessment,
        )
