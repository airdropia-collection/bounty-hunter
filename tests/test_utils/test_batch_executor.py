"""Tests for the batch execution engine with self-healing loop."""
from __future__ import annotations

from unittest.mock import patch

from src.utils.batch_executor import (
    BatchExecutor,
    BatchResult,
    BatchTarget,
    GateStatus,
    LoopState,
    diagnose_error,
)
from src.utils.polyglot_runner import LintResult, TestRunResult


# ──────────────────────────────────────────────────────────────────── #
# diagnose_error
# ──────────────────────────────────────────────────────────────────── #
def test_diagnose_missing_import():
    d = diagnose_error("ModuleNotFoundError: No module named 'solutions.issue_3_hook'")
    assert d is not None
    assert d["category"] == "missing_import"

def test_diagnose_broken_import():
    d = diagnose_error("ImportError: cannot import name 'check_command' from 'src.utils'")
    assert d is not None
    assert d["category"] == "broken_import"

def test_diagnose_name_error():
    d = diagnose_error("NameError: name 'undefined_var' is not defined")
    assert d is not None
    assert d["category"] == "undefined_variable"

def test_diagnose_syntax_error():
    d = diagnose_error("SyntaxError: invalid syntax")
    assert d is not None
    assert d["category"] == "syntax_error"

def test_diagnose_assertion_error():
    d = diagnose_error("AssertionError: assert 1 == 2")
    assert d is not None
    assert d["category"] == "assertion_mismatch"

def test_diagnose_ruff_naming():
    d = diagnose_error("E741 Ambiguous variable name 'l'")
    assert d is not None
    assert d["category"] == "ruff_naming"

def test_diagnose_ruff_unused_import():
    d = diagnose_error("F401 'os.path' imported but unused")
    assert d is not None
    assert d["category"] == "ruff_unused_import"

def test_diagnose_go_undefined():
    d = diagnose_error("undefined: foo in main.go")
    assert d is not None
    assert d["category"] == "go_undefined"

def test_diagnose_go_missing_package():
    d = diagnose_error("cannot find package foobar in any of /usr/local/go/src")
    assert d is not None
    assert d["category"] == "go_missing_package"

def test_diagnose_rust_error():
    d = diagnose_error("error[E0308]: mismatched types")
    assert d is not None
    assert d["category"] == "rust_compiler_error"

def test_diagnose_unknown_error():
    d = diagnose_error("something completely unknown went wrong")
    assert d is None

def test_diagnose_empty_string():
    d = diagnose_error("")
    assert d is None


# ──────────────────────────────────────────────────────────────────── #
# BatchTarget + BatchResult
# ──────────────────────────────────────────────────────────────────── #
def test_batch_result_format_record():
    result = BatchResult(
        identifier="owner/repo#123",
        financial_valuation="$10",
        gate_alpha=GateStatus.PASS,
        gate_beta=GateStatus.PASS,
        loop_state=LoopState.SUCCESS,
        cycles_consumed=0,
        diagnostic_exception=None,
        core_resolution_log="Tests passed.",
    )
    record = result.format_record()
    assert "[TARGET_BATCH_RECORD_START]" in record
    assert "owner/repo#123" in record
    assert "$10" in record
    assert "ALPHA: PASS" in record
    assert "BETA: PASS" in record
    assert "LOOP_STATE: SUCCESS" in record
    assert "CYCLES_CONSUMED: 0" in record
    assert "[TARGET_BATCH_RECORD_END]" in record


# ──────────────────────────────────────────────────────────────────── #
# BatchExecutor — gate logic
# ──────────────────────────────────────────────────────────────────── #
def test_gate_alpha_fail_low_confidence():
    """Target below 80% confidence should be skipped at Gate Alpha."""
    target = BatchTarget(
        identifier="test/repo#1",
        issue_title="Implement machine learning neural network in Rust with async tokio runtime",
        issue_body="Build a distributed ML inference engine",
        financial_value="$10",
    )
    executor = BatchExecutor(max_heal_cycles=3)
    results = executor.execute_batch([target])
    assert len(results) == 1
    assert results[0].gate_alpha == GateStatus.FAIL
    assert results[0].loop_state == LoopState.SKIPPED
    assert results[0].cycles_consumed == 0


def test_gate_alpha_pass_python():
    """Python target with standard complexity should pass Gate Alpha."""
    target = BatchTarget(
        identifier="test/repo#2",
        issue_title="Add a Python utility function for string parsing",
        issue_body="Write a Python function that parses strings using regex",
        financial_value="$5",
        project_dir=".",
    )
    executor = BatchExecutor(max_heal_cycles=0)  # don't actually run tests
    # Mock the healing loop to just return success
    with patch.object(executor, "_healing_loop") as mock_heal:
        mock_heal.return_value = BatchResult(
            identifier="test/repo#2",
            financial_valuation="$5",
            gate_alpha=GateStatus.PASS,
            gate_beta=GateStatus.PASS,
            loop_state=LoopState.SUCCESS,
            cycles_consumed=0,
            diagnostic_exception=None,
            core_resolution_log="Mocked success",
        )
        results = executor.execute_batch([target])
    assert results[0].gate_alpha == GateStatus.PASS


def test_gate_beta_fail_security_pattern():
    """Issue asking for hardcoded API keys should fail Gate Beta."""
    target = BatchTarget(
        identifier="test/repo#3",
        issue_title="Add Python function to hardcode api key in config",
        issue_body="Write a function that hardcodes the API key for convenience",
        financial_value="$10",
    )
    executor = BatchExecutor(max_heal_cycles=3)
    results = executor.execute_batch([target])
    # Gate Alpha might pass (Python, standard complexity)
    # But Gate Beta should fail (security anti-pattern)
    if results[0].gate_alpha == GateStatus.PASS:
        assert results[0].gate_beta == GateStatus.FAIL
        assert results[0].loop_state == LoopState.SKIPPED


def test_gate_beta_pass_clean_issue():
    """Clean issue should pass both gates."""
    target = BatchTarget(
        identifier="test/repo#4",
        issue_title="Add Python utility for string parsing",
        issue_body="Write a function that parses strings safely",
        financial_value="$1",
        project_dir=".",
    )
    executor = BatchExecutor(max_heal_cycles=0)
    with patch.object(executor, "_healing_loop") as mock_heal:
        mock_heal.return_value = BatchResult(
            identifier="test/repo#4",
            financial_valuation="$1",
            gate_alpha=GateStatus.PASS,
            gate_beta=GateStatus.PASS,
            loop_state=LoopState.SUCCESS,
            cycles_consumed=0,
            diagnostic_exception=None,
            core_resolution_log="Mocked",
        )
        results = executor.execute_batch([target])
    assert results[0].gate_beta == GateStatus.PASS


# ──────────────────────────────────────────────────────────────────── #
# BatchExecutor — self-healing loop
# ──────────────────────────────────────────────────────────────────── #
def test_healing_loop_success_first_try():
    """Tests pass on first attempt → SUCCESS, 0 cycles consumed."""
    target = BatchTarget(
        identifier="test/repo#5",
        issue_title="Python utility function",
        issue_body="Write a function",
        project_dir=".",
    )
    executor = BatchExecutor(max_heal_cycles=3, test_timeout=5, lint_timeout=5)

    mock_test = TestRunResult(
        language="python", command="pytest", exit_code=0,
        stdout="5 passed", stderr="", passed=True, pass_count=5,
    )
    mock_lint = LintResult(
        language="python", command="ruff", exit_code=0,
        stdout="", stderr="", passed=True,
    )
    with patch("src.utils.batch_executor.run_tests", return_value=mock_test):
        with patch("src.utils.batch_executor.run_lint", return_value=mock_lint):
            results = executor.execute_batch([target])
    assert results[0].loop_state == LoopState.SUCCESS
    assert results[0].cycles_consumed == 0


def test_healing_loop_success_after_heal():
    """Tests fail first, then pass → AUTONOMOUS_HEALED, 1 cycle consumed."""
    target = BatchTarget(
        identifier="test/repo#6",
        issue_title="Python utility function",
        issue_body="Write a function",
        project_dir=".",
    )
    executor = BatchExecutor(max_heal_cycles=3, test_timeout=5, lint_timeout=5)

    fail_test = TestRunResult(
        language="python", command="pytest", exit_code=1,
        stdout="", stderr="NameError: name 'foo' is not defined", passed=False,
    )
    pass_test = TestRunResult(
        language="python", command="pytest", exit_code=0,
        stdout="5 passed", stderr="", passed=True, pass_count=5,
    )
    pass_lint = LintResult(
        language="python", command="ruff", exit_code=0,
        stdout="", stderr="", passed=True,
    )
    # First call: fail; second call: pass
    with patch("src.utils.batch_executor.run_tests", side_effect=[fail_test, pass_test]):
        with patch("src.utils.batch_executor.run_lint", return_value=pass_lint):
            results = executor.execute_batch([target])
    assert results[0].loop_state == LoopState.AUTONOMOUS_HEALED
    assert results[0].cycles_consumed == 1


def test_healing_loop_fail_after_max_cycles():
    """Tests fail all 3+1 cycles → FAILED, fail-forward."""
    target = BatchTarget(
        identifier="test/repo#7",
        issue_title="Python utility function",
        issue_body="Write a function",
        project_dir=".",
    )
    executor = BatchExecutor(max_heal_cycles=2, test_timeout=5, lint_timeout=5)

    fail_test = TestRunResult(
        language="python", command="pytest", exit_code=1,
        stdout="", stderr="AssertionError: assert 1 == 2", passed=False,
    )
    fail_lint = LintResult(
        language="python", command="ruff", exit_code=1,
        stdout="error", stderr="F401 unused import", passed=False,
    )
    with patch("src.utils.batch_executor.run_tests", return_value=fail_test):
        with patch("src.utils.batch_executor.run_lint", return_value=fail_lint):
            results = executor.execute_batch([target])
    assert results[0].loop_state == LoopState.FAILED
    assert results[0].cycles_consumed == 2
    assert results[0].diagnostic_exception is not None


def test_batch_fail_forward_does_not_crash():
    """Multiple targets — one fails, next still processes."""
    targets = [
        BatchTarget(
            identifier="test/repo#8",
            issue_title="ML neural network in Rust async runtime",
            issue_body="Build distributed ML engine",
            project_dir=".",
        ),
        BatchTarget(
            identifier="test/repo#9",
            issue_title="Python utility function",
            issue_body="Write a function",
            project_dir=".",
        ),
    ]
    executor = BatchExecutor(max_heal_cycles=0, test_timeout=5, lint_timeout=5)

    mock_test = TestRunResult(
        language="python", command="pytest", exit_code=0,
        stdout="1 passed", stderr="", passed=True, pass_count=1,
    )
    mock_lint = LintResult(
        language="python", command="ruff", exit_code=0,
        stdout="", stderr="", passed=True,
    )
    with patch("src.utils.batch_executor.run_tests", return_value=mock_test):
        with patch("src.utils.batch_executor.run_lint", return_value=mock_lint):
            results = executor.execute_batch(targets)
    assert len(results) == 2
    # First target: Gate Alpha FAIL (Rust ML, confidence < 80%)
    assert results[0].loop_state == LoopState.SKIPPED
    # Second target: should process normally
    assert results[1].loop_state in (LoopState.SUCCESS, LoopState.AUTONOMOUS_HEALED)


def test_value_agnostic_processing():
    """$1 and $100 targets are processed identically — no value filtering."""
    targets = [
        BatchTarget(
            identifier="test/repo#10",
            issue_title="Add Python utility function",
            issue_body="Write a parsing function",
            financial_value="$1",
            project_dir=".",
        ),
        BatchTarget(
            identifier="test/repo#11",
            issue_title="Add Python utility function",
            issue_body="Write a parsing function",
            financial_value="$100",
            project_dir=".",
        ),
    ]
    executor = BatchExecutor(max_heal_cycles=0, test_timeout=5, lint_timeout=5)

    mock_test = TestRunResult(
        language="python", command="pytest", exit_code=0,
        stdout="1 passed", stderr="", passed=True, pass_count=1,
    )
    mock_lint = LintResult(
        language="python", command="ruff", exit_code=0,
        stdout="", stderr="", passed=True,
    )
    with patch("src.utils.batch_executor.run_tests", return_value=mock_test):
        with patch("src.utils.batch_executor.run_lint", return_value=mock_lint):
            results = executor.execute_batch(targets)
    # Both should succeed — value doesn't affect processing
    assert results[0].loop_state == LoopState.SUCCESS
    assert results[1].loop_state == LoopState.SUCCESS
    # Values are recorded for telemetry only
    assert results[0].financial_valuation == "$1"
    assert results[1].financial_valuation == "$100"
