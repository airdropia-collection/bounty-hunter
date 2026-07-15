"""Tests for the report drafter."""
from src.analyzers.vuln_detector import Finding
from src.reporters.drafter import ReportDrafter


def test_draft_returns_string():
    """Report drafter should return a string (even if AI is unavailable)."""
    f = Finding(
        id="test-1",
        title="Test vulnerability",
        severity="Medium",
        confidence=0.7,
        description="A test vulnerability",
        impact="Test impact",
        recommendation="Test recommendation",
    )
    drafter = ReportDrafter()
    # AI will fail (no keys in test env) — should return fallback report
    report = drafter.draft(f, source_code="contract Test {}", platform="immunefi")
    assert isinstance(report, str)
    assert "Test vulnerability" in report
    assert "Error" in report or "Summary" in report  # fallback or AI-generated


def test_draft_with_empty_source():
    f = Finding(
        id="x", title="X", severity="Low", confidence=0.5,
        description="", impact="", recommendation="",
    )
    drafter = ReportDrafter()
    report = drafter.draft(f, source_code="", platform="code4rena")
    assert isinstance(report, str)
