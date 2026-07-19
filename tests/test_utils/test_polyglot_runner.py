"""Tests for the polyglot test runner."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from src.utils.polyglot_runner import (
    TestRunResult,
    _parse_cargo_test_output,
    _parse_go_test_output,
    _parse_npm_test_output,
    _parse_pytest_output,
    run_full_verification,
    run_lint,
    run_tests,
)


# ──────────────────────────────────────────────────────────────────── #
# Output parsers
# ──────────────────────────────────────────────────────────────────── #
def test_parse_pytest_passed():
    p, f = _parse_pytest_output("235 passed in 1.33s", "")
    assert p == 235
    assert f is None

def test_parse_pytest_mixed():
    p, f = _parse_pytest_output("3 failed, 232 passed in 2.5s", "")
    assert p == 232
    assert f == 3

def test_parse_pytest_no_match():
    p, f = _parse_pytest_output("no tests ran", "")
    assert p is None
    assert f is None

def test_parse_go_test_ok():
    p, f = _parse_go_test_output("ok  \tgithub.com/pkg/sub\t0.5s\nok  \tgithub.com/pkg/main\t0.3s", "")
    assert p == 2
    assert f == 0

def test_parse_go_test_fail():
    p, f = _parse_go_test_output("FAIL\tgithub.com/pkg/sub [build failed]", "")
    assert p == 0
    assert f == 1

def test_parse_cargo_test():
    p, f = _parse_cargo_test_output("running 5 tests\ntest result: ok. 5 passed; 0 failed", "")
    assert p == 5
    assert f == 0

def test_parse_npm_jest():
    p, f = _parse_npm_test_output("Tests: 5 passed, 0 failed", "")
    assert p == 5
    assert f == 0

def test_parse_npm_mocha():
    p, f = _parse_npm_test_output("  3 passing\n  1 failing", "")
    assert p == 3
    assert f == 1


# ──────────────────────────────────────────────────────────────────── #
# run_tests (mocked subprocess)
# ──────────────────────────────────────────────────────────────────── #
def test_run_tests_python_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "5 passed in 0.5s"
    mock_result.stderr = ""
    with patch("subprocess.run", return_value=mock_result):
        result = run_tests("python", ".")
    assert result.passed is True
    assert result.exit_code == 0
    assert result.pass_count == 5
    assert result.language == "python"

def test_run_tests_python_failure():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "2 failed, 3 passed"
    mock_result.stderr = ""
    with patch("subprocess.run", return_value=mock_result):
        result = run_tests("python", ".")
    assert result.passed is False
    assert result.fail_count == 2
    assert result.pass_count == 3

def test_run_tests_go_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "ok  \tgithub.com/pkg\t0.5s"
    mock_result.stderr = ""
    with patch("subprocess.run", return_value=mock_result):
        result = run_tests("go", ".")
    assert result.passed is True
    assert result.pass_count == 1

def test_run_tests_rust_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "test result: ok. 10 passed; 0 failed"
    mock_result.stderr = ""
    with patch("subprocess.run", return_value=mock_result):
        result = run_tests("rust", ".")
    assert result.passed is True
    assert result.pass_count == 10

def test_run_tests_typescript_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Tests: 8 passed, 0 failed"
    mock_result.stderr = ""
    with patch("subprocess.run", return_value=mock_result):
        result = run_tests("typescript", ".")
    assert result.passed is True
    assert result.pass_count == 8

def test_run_tests_unsupported_language():
    result = run_tests("cobol", ".")
    assert result.passed is False
    assert "not supported" in result.stderr.lower()

def test_run_tests_command_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError("go not found")):
        result = run_tests("go", ".")
    assert result.passed is False
    assert "not found" in result.stderr.lower()

def test_run_tests_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=5)):
        result = run_tests("python", ".", timeout=5)
    assert result.passed is False
    assert "timed out" in result.stderr.lower()


# ──────────────────────────────────────────────────────────────────── #
# run_lint (mocked subprocess)
# ──────────────────────────────────────────────────────────────────── #
def test_run_lint_python_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "All checks passed!"
    mock_result.stderr = ""
    with patch("subprocess.run", return_value=mock_result):
        result = run_lint("python", ".")
    assert result.passed is True
    assert result.error_count == 0

def test_run_lint_python_failure():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "error: unused import\nwarning: line too long"
    mock_result.stderr = ""
    with patch("subprocess.run", return_value=mock_result):
        result = run_lint("python", ".")
    assert result.passed is False
    assert result.error_count == 2

def test_run_lint_unsupported_language():
    result = run_lint("cobol", ".")
    assert result.passed is True  # don't block on unsupported lint
    assert result.error_count == 0

def test_run_lint_command_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError("ruff not found")):
        result = run_lint("python", ".")
    assert result.passed is False


# ──────────────────────────────────────────────────────────────────── #
# run_full_verification
# ──────────────────────────────────────────────────────────────────── #
def test_full_verification_both_pass():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "5 passed"
    mock_result.stderr = ""
    with patch("subprocess.run", return_value=mock_result):
        test_result, lint_result = run_full_verification("python", ".")
    assert test_result.passed is True
    assert lint_result.passed is True

def test_full_verification_test_fail_lint_pass():
    mock_test = MagicMock()
    mock_test.returncode = 1
    mock_test.stdout = "2 failed, 3 passed"
    mock_test.stderr = ""
    mock_lint = MagicMock()
    mock_lint.returncode = 0
    mock_lint.stdout = "All checks passed!"
    mock_lint.stderr = ""
    with patch("subprocess.run", side_effect=[mock_test, mock_lint]):
        test_result, lint_result = run_full_verification("python", ".")
    assert test_result.passed is False
    assert lint_result.passed is True


# ──────────────────────────────────────────────────────────────────── #
# TestRunResult.summary property
# ──────────────────────────────────────────────────────────────────── #
def test_test_result_summary_passed():
    result = TestRunResult(
        language="python",
        command="pytest",
        exit_code=0,
        stdout="",
        stderr="",
        passed=True,
        pass_count=5,
        fail_count=0,
    )
    summary = result.summary
    assert "python" in summary
    assert "passed=5" in summary
    assert "✅" in summary

def test_test_result_summary_failed():
    result = TestRunResult(
        language="go",
        command="go test",
        exit_code=1,
        stdout="",
        stderr="",
        passed=False,
        pass_count=3,
        fail_count=2,
    )
    summary = result.summary
    assert "go" in summary
    assert "failed=2" in summary
    assert "❌" in summary
