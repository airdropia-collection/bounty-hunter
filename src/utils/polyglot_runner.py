"""
Polyglot Test Runner — Multi-language test execution harness.

Runs language-appropriate test commands in a subprocess and captures:
  - Exit code (0 = pass, non-zero = fail)
  - stdout/stderr output
  - Parsed pass/fail counts (when available)

Supported languages:
  - Python: pytest + ruff
  - TypeScript/JavaScript: npm test + eslint
  - Go: go test + go vet
  - Rust: cargo test + cargo clippy
  - Bash: bash -n + shellcheck

Usage:
    from src.utils.polyglot_runner import run_tests, run_lint, TestRunResult

    result = run_tests(language="python", project_dir="/path/to/repo")
    if result.passed:
        print(f"✅ {result.pass_count} tests passed")
    else:
        print(f"❌ {result.stderr[:200]}")
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger("polyglot_runner")


# ──────────────────────────────────────────────────────────────────── #
# Test commands per language
# ──────────────────────────────────────────────────────────────────── #

TEST_COMMANDS: dict[str, list[str]] = {
    "python": ["python", "-m", "pytest", "-q", "--tb=short"],
    "typescript": ["npm", "test", "--", "--reporter=dot"],
    "javascript": ["npm", "test", "--", "--reporter=dot"],
    "go": ["go", "test", "./..."],
    "rust": ["cargo", "test"],
    "bash": ["bash", "-n"],  # syntax check only (no unit test framework)
}

LINT_COMMANDS: dict[str, list[str]] = {
    "python": ["ruff", "check"],
    "typescript": ["npx", "eslint", "--max-warnings", "0"],
    "javascript": ["npx", "eslint", "--max-warnings", "0"],
    "go": ["go", "vet", "./..."],
    "rust": ["cargo", "clippy", "--", "-D", "warnings"],
    "bash": ["shellcheck"],
}


# ──────────────────────────────────────────────────────────────────── #
# Result dataclasses
# ──────────────────────────────────────────────────────────────────── #

@dataclass
class TestRunResult:
    """Result of running a test suite."""
    language: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool
    pass_count: int | None = None
    fail_count: int | None = None
    duration_seconds: float = 0.0

    @property
    def summary(self) -> str:
        parts = [f"[{self.language}] exit={self.exit_code}"]
        if self.pass_count is not None:
            parts.append(f"passed={self.pass_count}")
        if self.fail_count is not None:
            parts.append(f"failed={self.fail_count}")
        parts.append("✅" if self.passed else "❌")
        return " ".join(parts)


@dataclass
class LintResult:
    """Result of running a linter."""
    language: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool
    error_count: int = 0


# ──────────────────────────────────────────────────────────────────── #
# Output parsers — extract pass/fail counts from test output
# ──────────────────────────────────────────────────────────────────── #

def _parse_pytest_output(stdout: str, stderr: str) -> tuple[int | None, int | None]:
    """Parse pytest output for pass/fail counts."""
    text = stdout + stderr
    # Match: "235 passed" or "3 failed, 232 passed"
    pass_match = re.search(r'(\d+) passed', text)
    fail_match = re.search(r'(\d+) failed', text)
    pass_count = int(pass_match.group(1)) if pass_match else None
    fail_count = int(fail_match.group(1)) if fail_match else None
    return pass_count, fail_count


def _parse_go_test_output(stdout: str, stderr: str) -> tuple[int | None, int | None]:
    """Parse go test output."""
    text = stdout + stderr
    # Match: "ok \tpkg\t0.5s" or "FAIL\tpkg [build failed]"
    ok_count = text.count("ok  \t") + text.count("ok\t")
    fail_count = text.count("FAIL\t") + text.count("FAIL ")
    if ok_count or fail_count:
        return ok_count, fail_count
    return None, None


def _parse_cargo_test_output(stdout: str, stderr: str) -> tuple[int | None, int | None]:
    """Parse cargo test output."""
    text = stdout + stderr
    pass_match = re.search(r'(\d+) passed', text)
    fail_match = re.search(r'(\d+) failed', text)
    pass_count = int(pass_match.group(1)) if pass_match else None
    fail_count = int(fail_match.group(1)) if fail_match else None
    return pass_count, fail_count


def _parse_npm_test_output(stdout: str, stderr: str) -> tuple[int | None, int | None]:
    """Parse npm test output (jest/vitest/mocha)."""
    text = stdout + stderr
    # Jest: "Tests: 5 passed, 0 failed"
    pass_match = re.search(r'(\d+)\s+passing', text) or re.search(r'(\d+)\s+passed', text)
    fail_match = re.search(r'(\d+)\s+failing', text) or re.search(r'(\d+)\s+failed', text)
    pass_count = int(pass_match.group(1)) if pass_match else None
    fail_count = int(fail_match.group(1)) if fail_match else None
    return pass_count, fail_count


PARSERS = {
    "python": _parse_pytest_output,
    "go": _parse_go_test_output,
    "rust": _parse_cargo_test_output,
    "typescript": _parse_npm_test_output,
    "javascript": _parse_npm_test_output,
}


# ──────────────────────────────────────────────────────────────────── #
# Core execution
# ──────────────────────────────────────────────────────────────────── #

def run_tests(
    language: str,
    project_dir: str = ".",
    timeout: int = 120,
) -> TestRunResult:
    """Run the test suite for a given language.

    Args:
        language: One of: python, typescript, javascript, go, rust, bash.
        project_dir: Path to the project directory.
        timeout: Maximum seconds to wait for tests to complete.

    Returns:
        TestRunResult with exit code, output, and parsed counts.
    """
    import time

    cmd = TEST_COMMANDS.get(language)
    if not cmd:
        return TestRunResult(
            language=language,
            command="(unsupported)",
            exit_code=-1,
            stdout="",
            stderr=f"Language '{language}' not supported by polyglot runner",
            passed=False,
        )

    cmd_str = " ".join(cmd)
    log.info("Running tests: %s in %s", cmd_str, project_dir)

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start

        # Parse pass/fail counts
        parser = PARSERS.get(language)
        pass_count, fail_count = (None, None)
        if parser:
            pass_count, fail_count = parser(result.stdout, result.stderr)

        return TestRunResult(
            language=language,
            command=cmd_str,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            passed=result.returncode == 0,
            pass_count=pass_count,
            fail_count=fail_count,
            duration_seconds=round(duration, 2),
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return TestRunResult(
            language=language,
            command=cmd_str,
            exit_code=-1,
            stdout="",
            stderr=f"Test timed out after {timeout}s",
            passed=False,
            duration_seconds=round(duration, 2),
        )
    except FileNotFoundError:
        return TestRunResult(
            language=language,
            command=cmd_str,
            exit_code=-1,
            stdout="",
            stderr=f"Command not found: {cmd[0]}",
            passed=False,
        )


def run_lint(
    language: str,
    project_dir: str = ".",
    timeout: int = 60,
) -> LintResult:
    """Run the linter for a given language.

    Args:
        language: One of: python, typescript, javascript, go, rust, bash.
        project_dir: Path to the project directory.
        timeout: Maximum seconds to wait.

    Returns:
        LintResult with exit code and error count.
    """
    cmd = LINT_COMMANDS.get(language)
    if not cmd:
        return LintResult(
            language=language,
            command="(unsupported)",
            exit_code=-1,
            stdout="",
            stderr=f"No linter configured for '{language}'",
            passed=True,  # don't block on unsupported lint
            error_count=0,
        )

    cmd_str = " ".join(cmd)
    log.info("Running lint: %s in %s", cmd_str, project_dir)

    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Count errors from output
        error_count = 0
        if result.returncode != 0:
            # Count lines that look like errors
            error_lines = [l for l in (result.stdout + result.stderr).split("\n")
                          if l.strip() and ("error" in l.lower() or "warning" in l.lower())]
            error_count = len(error_lines)

        return LintResult(
            language=language,
            command=cmd_str,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            passed=result.returncode == 0,
            error_count=error_count,
        )
    except subprocess.TimeoutExpired:
        return LintResult(
            language=language,
            command=cmd_str,
            exit_code=-1,
            stdout="",
            stderr=f"Lint timed out after {timeout}s",
            passed=False,
        )
    except FileNotFoundError:
        return LintResult(
            language=language,
            command=cmd_str,
            exit_code=-1,
            stdout="",
            stderr=f"Command not found: {cmd[0]}",
            passed=False,
        )


def run_full_verification(
    language: str,
    project_dir: str = ".",
    test_timeout: int = 120,
    lint_timeout: int = 60,
) -> tuple[TestRunResult, LintResult]:
    """Run both tests and lint for a project.

    Returns:
        Tuple of (TestRunResult, LintResult).
    """
    test_result = run_tests(language, project_dir, test_timeout)
    lint_result = run_lint(language, project_dir, lint_timeout)
    return test_result, lint_result
