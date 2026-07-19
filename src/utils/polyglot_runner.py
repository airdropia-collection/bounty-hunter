"""
Polyglot Test Runner — Multi-language test execution harness.

Runs language-appropriate test commands in a subprocess and captures:
  - Exit code (0 = pass, non-zero = fail)
  - stdout/stderr output
  - Parsed pass/fail counts (when available)

Supported languages:
  - Python: pytest + ruff
  - TypeScript/JavaScript: npm test + eslint
  - Go: go mod tidy → go test -v → go vet (with mod cache + verbose diagnostics)
  - Rust: cargo check --message-format=json → cargo test → cargo clippy
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

import json
import re
import subprocess
from dataclasses import dataclass

from src.utils.logger import get_logger

log = get_logger("polyglot_runner")


# ──────────────────────────────────────────────────────────────────── #
# Test commands per language
# ──────────────────────────────────────────────────────────────────── #

TEST_COMMANDS: dict[str, list[str]] = {
    "python": ["python", "-m", "pytest", "-q", "--tb=short"],
    "typescript": ["npm", "test", "--", "--reporter=dot"],
    "javascript": ["npm", "test", "--", "--reporter=dot"],
    "go": ["go", "test", "-v", "./..."],
    "rust": ["cargo", "test"],
    "bash": ["bash", "-n"],
}

LINT_COMMANDS: dict[str, list[str]] = {
    "python": ["ruff", "check"],
    "typescript": ["npx", "eslint", "--max-warnings", "0"],
    "javascript": ["npx", "eslint", "--max-warnings", "0"],
    "go": ["go", "vet", "./..."],
    "rust": ["cargo", "clippy", "--", "-D", "warnings"],
    "bash": ["shellcheck"],
}

# Pre-test setup commands (run before tests to ensure clean build)
PRE_TEST_COMMANDS: dict[str, list[list[str]]] = {
    "go": [
        ["go", "mod", "tidy"],
    ],
    "rust": [
        ["cargo", "check", "--message-format=json"],
    ],
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
    diagnostics: list[dict] | None = None

    @property
    def summary(self) -> str:
        parts = [f"[{self.language}] exit={self.exit_code}"]
        if self.pass_count is not None:
            parts.append(f"passed={self.pass_count}")
        if self.fail_count is not None:
            parts.append(f"failed={self.fail_count}")
        if self.diagnostics:
            parts.append(f"diagnostics={len(self.diagnostics)}")
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
    pass_match = re.search(r'(\d+) passed', text)
    fail_match = re.search(r'(\d+) failed', text)
    pass_count = int(pass_match.group(1)) if pass_match else None
    fail_count = int(fail_match.group(1)) if fail_match else None
    return pass_count, fail_count


def _parse_go_test_output(stdout: str, stderr: str) -> tuple[int | None, int | None]:
    """Parse go test -v output for pass/fail counts.

    Verbose Go output format:
        === RUN   TestFoo
        --- PASS: TestFoo (0.00s)
        --- FAIL: TestBar (0.00s)
        PASS
        ok      pkg     0.5s
    """
    text = stdout + stderr
    # Count individual test results from verbose output
    pass_count = len(re.findall(r'--- PASS:', text))
    fail_count = len(re.findall(r'--- FAIL:', text))
    if pass_count or fail_count:
        return pass_count, fail_count
    # Fallback: count package-level results
    ok_count = text.count("ok  \t") + text.count("ok\t")
    fail_pkgs = text.count("FAIL\t") + text.count("FAIL ")
    if ok_count or fail_pkgs:
        return ok_count, fail_pkgs
    return None, None


def _parse_cargo_test_output(stdout: str, stderr: str) -> tuple[int | None, int | None]:
    """Parse cargo test output for pass/fail counts.

    Cargo output format:
        running 10 tests
        test foo::test_bar ... ok
        test foo::test_baz ... FAILED
        test result: FAILED. 9 passed; 1 failed; 0 ignored
    """
    text = stdout + stderr
    pass_match = re.search(r'(\d+) passed', text)
    fail_match = re.search(r'(\d+) failed', text)
    pass_count = int(pass_match.group(1)) if pass_match else None
    fail_count = int(fail_match.group(1)) if fail_match else None
    return pass_count, fail_count


def _parse_npm_test_output(stdout: str, stderr: str) -> tuple[int | None, int | None]:
    """Parse npm test output (jest/vitest/mocha)."""
    text = stdout + stderr
    pass_match = re.search(r'(\d+)\s+passing', text) or re.search(r'(\d+)\s+passed', text)
    fail_match = re.search(r'(\d+)\s+failing', text) or re.search(r'(\d+)\s+failed', text)
    pass_count = int(pass_match.group(1)) if pass_match else None
    fail_count = int(fail_match.group(1)) if fail_match else None
    return pass_count, fail_count


# ──────────────────────────────────────────────────────────────────── #
# Rust JSON diagnostics parser (cargo check --message-format=json)
# ──────────────────────────────────────────────────────────────────── #

def _parse_cargo_json_diagnostics(stdout: str, stderr: str = "") -> list[dict]:
    """Parse cargo check JSON output into structured diagnostics.

    Each line of cargo check --message-format=json is a JSON object.
    We extract compiler-error and compiler-warning messages with their
    file/line/column info for the self-healing loop.

    Returns list of diagnostic dicts:
        [{
            "level": "error" | "warning",
            "message": "...",
            "file": "src/main.rs",
            "line": 42,
            "column": 5,
            "code": "E0308",  # Rust error code
        }]
    """
    diagnostics: list[dict] = []
    for line in stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        # Only process compiler messages
        if msg.get("reason") != "compiler-message":
            continue

        level = msg.get("level", "unknown")  # "error", "warning", "note"
        if level not in ("error", "warning"):
            continue

        message_obj = msg.get("message", {})
        message_text = message_obj.get("message", "")
        code_obj = message_obj.get("code", {})
        code = code_obj.get("code", "") if code_obj else ""

        # Extract primary span (file/line/col)
        spans = message_obj.get("spans", [])
        file_path = ""
        line_num = 0
        col_num = 0
        for span in spans:
            if span.get("is_primary", False):
                file_path = span.get("file_name", "")
                line_num = span.get("line_start", 0)
                col_num = span.get("column_start", 0)
                break

        diagnostics.append({
            "level": level,
            "message": message_text,
            "file": file_path,
            "line": line_num,
            "column": col_num,
            "code": code,
        })

    return diagnostics


# ──────────────────────────────────────────────────────────────────── #
# Go error parser (extracts build/test failures from go output)
# ──────────────────────────────────────────────────────────────────── #

def _parse_go_errors(stdout: str, stderr: str) -> list[dict]:
    """Parse Go build/test errors for structured diagnostics.

    Go error format:
        ./main.go:10:2: undefined: foo
        ./main.go:15:1: missing return at end of function
        # package
        ./main.go:5:2: imported and not used: "fmt"
    """
    diagnostics: list[dict] = []
    text = stderr + "\n" + stdout

    # Match: ./file.go:line:col: message
    pattern = re.compile(
        r'(?:(?:#|\s*)[\w./-]+)\s*\n?'  # optional package header
        r'((?:\./|/)?[\w./-]+\.go):(\d+)(?::(\d+))?:\s*(.+)'  # file:line:col: msg
    )

    for match in pattern.finditer(text):
        file_path = match.group(1)
        line_num = int(match.group(2)) if match.group(2) else 0
        col_num = int(match.group(3)) if match.group(3) else 0
        message = match.group(4).strip()

        # Classify
        level = "error"
        if "warning" in message.lower():
            level = "warning"

        diagnostics.append({
            "level": level,
            "message": message,
            "file": file_path,
            "line": line_num,
            "column": col_num,
            "code": "",  # Go doesn't use error codes
        })

    return diagnostics


PARSERS = {
    "python": _parse_pytest_output,
    "go": _parse_go_test_output,
    "rust": _parse_cargo_test_output,
    "typescript": _parse_npm_test_output,
    "javascript": _parse_npm_test_output,
}

DIAGNOSTIC_PARSERS = {
    "go": _parse_go_errors,
    "rust": _parse_cargo_json_diagnostics,
}


# ──────────────────────────────────────────────────────────────────── #
# Core execution
# ──────────────────────────────────────────────────────────────────── #

def _run_pre_test_setup(language: str, project_dir: str, timeout: int = 60) -> tuple[bool, str, str]:
    """Run pre-test setup commands (e.g., go mod tidy, cargo check).

    Returns (success, stdout, stderr).
    """
    commands = PRE_TEST_COMMANDS.get(language, [])
    all_stdout = ""
    all_stderr = ""

    for cmd in commands:
        cmd_str = " ".join(cmd)
        log.info("Pre-test setup: %s in %s", cmd_str, project_dir)
        try:
            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            all_stdout += result.stdout
            all_stderr += result.stderr
            if result.returncode != 0:
                log.warning("Pre-test setup failed: %s (exit %d)", cmd_str, result.returncode)
                return False, all_stdout, all_stderr
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            log.warning("Pre-test setup error: %s", exc)
            return False, all_stdout, str(exc)

    return True, all_stdout, all_stderr


def run_tests(
    language: str,
    project_dir: str = ".",
    timeout: int = 120,
) -> TestRunResult:
    """Run the test suite for a given language.

    For Go: runs `go mod tidy` first, then `go test -v ./...`
    For Rust: runs `cargo check --message-format=json` first, then `cargo test`

    Args:
        language: One of: python, typescript, javascript, go, rust, bash.
        project_dir: Path to the project directory.
        timeout: Maximum seconds to wait for tests to complete.

    Returns:
        TestRunResult with exit code, output, parsed counts, and diagnostics.
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

    # Run pre-test setup (go mod tidy, cargo check)
    setup_ok, setup_stdout, setup_stderr = _run_pre_test_setup(language, project_dir)

    # Parse diagnostics from pre-test setup (especially cargo check JSON)
    diagnostics: list[dict] = []
    diag_parser = DIAGNOSTIC_PARSERS.get(language)
    if diag_parser and setup_stdout:
        diagnostics = diag_parser(setup_stdout, setup_stderr)

    # If pre-test setup failed (e.g., cargo check found errors), return early
    if not setup_ok and language == "rust":
        log.warning("Rust cargo check failed — skipping cargo test")
        return TestRunResult(
            language=language,
            command="cargo check → cargo test",
            exit_code=1,
            stdout=setup_stdout,
            stderr=setup_stderr,
            passed=False,
            diagnostics=diagnostics,
        )

    if not setup_ok and language == "go":
        log.warning("Go mod tidy failed — continuing with tests anyway")
        # Go mod tidy failure is non-fatal (may just be missing go.sum)

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

        # Combine pre-test + test output
        combined_stdout = setup_stdout + "\n" + result.stdout
        combined_stderr = setup_stderr + "\n" + result.stderr

        # Parse pass/fail counts
        parser = PARSERS.get(language)
        pass_count, fail_count = (None, None)
        if parser:
            pass_count, fail_count = parser(result.stdout, result.stderr)

        # Parse additional diagnostics from test output
        if diag_parser:
            test_diags = diag_parser(result.stdout, result.stderr)
            diagnostics.extend(test_diags)

        return TestRunResult(
            language=language,
            command=f"{' → '.join([' '.join(c) for c in PRE_TEST_COMMANDS.get(language, [])])} → {cmd_str}"
                  if PRE_TEST_COMMANDS.get(language) else cmd_str,
            exit_code=result.returncode,
            stdout=combined_stdout,
            stderr=combined_stderr,
            passed=result.returncode == 0,
            pass_count=pass_count,
            fail_count=fail_count,
            duration_seconds=round(duration, 2),
            diagnostics=diagnostics if diagnostics else None,
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
            diagnostics=diagnostics if diagnostics else None,
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
            passed=True,
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

        error_count = 0
        if result.returncode != 0:
            error_lines = [line for line in (result.stdout + result.stderr).split("\n")
                          if line.strip() and ("error" in line.lower() or "warning" in line.lower())]
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

    For Go: go mod tidy → go test -v ./... → go vet ./...
    For Rust: cargo check --message-format=json → cargo test → cargo clippy

    Returns:
        Tuple of (TestRunResult, LintResult).
    """
    test_result = run_tests(language, project_dir, test_timeout)
    lint_result = run_lint(language, project_dir, lint_timeout)
    return test_result, lint_result
