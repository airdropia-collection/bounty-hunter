"""Tests for the health check module."""
import pytest

from src.health import (
    run_all_checks,
    print_report,
    wake_operator_if_needed,
    Check,
)


def test_run_all_checks_returns_list():
    checks = run_all_checks()
    assert isinstance(checks, list)
    assert len(checks) > 0
    # Should include these
    names = [c.name for c in checks]
    assert "gemini_api_key" in names
    assert "github" in names
    assert "dry_run" in names


def test_print_report_no_errors(capsys):
    checks = [Check("test", True, "all good", "info")]
    code = print_report(checks)
    assert code == 0
    out = capsys.readouterr().out
    assert "All checks passed" in out


def test_print_report_with_errors(capsys):
    checks = [
        Check("bad", False, "missing", "error"),
        Check("good", True, "ok", "info"),
    ]
    code = print_report(checks)
    assert code == 1
    out = capsys.readouterr().out
    assert "ERRORS" in out


def test_print_report_with_warnings(capsys):
    checks = [Check("warn", True, "degraded", "warning")]
    code = print_report(checks)
    assert code == 0
    out = capsys.readouterr().out
    assert "WARNINGS" in out


def test_wake_operator_if_needed_no_errors(monkeypatch):
    # No errors → should not wake operator
    checks = [Check("ok", True, "fine", "info")]
    # Should not raise even in dry-run mode
    wake_operator_if_needed(checks)


def test_wake_operator_if_needed_with_errors_dry_run(monkeypatch):
    # Errors but no GitHub creds → should log warning, not crash
    for key in ["GH_PAT", "GH_REPO"]:
        monkeypatch.delenv(key, raising=False)
    checks = [Check("bad", False, "missing", "error")]
    wake_operator_if_needed(checks)  # should not raise
