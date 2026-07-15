"""Tests for the vulnerability detector."""
from src.analyzers.vuln_detector import Finding, VulnerabilityDetector


def test_finding_creation():
    f = Finding(
        id="test-1",
        title="Reentrancy in withdraw()",
        severity="High",
        confidence=0.8,
        description="The withdraw function can be re-entered",
        impact="Attacker can drain contract balance",
        recommendation="Use checks-effects-interactions pattern",
    )
    assert f.severity == "High"
    assert f.confidence == 0.8


def test_finding_to_dict():
    f = Finding(
        id="test-1",
        title="Test",
        severity="Medium",
        confidence=0.5,
        description="desc",
        impact="impact",
        recommendation="rec",
    )
    d = f.to_dict()
    assert d["title"] == "Test"
    assert d["severity"] == "Medium"
    assert d["confidence"] == 0.5
    assert "line_numbers" in d


def test_finding_defaults():
    f = Finding(
        id="x",
        title="x",
        severity="Low",
        confidence=0.3,
        description="",
        impact="",
        recommendation="",
    )
    assert f.line_numbers == []
    assert f.poc_suggestion == ""
    assert f.swc_id == ""


def test_detector_empty_source():
    """Empty source code should return no findings."""
    from unittest.mock import patch, MagicMock
    detector = VulnerabilityDetector()
    # Empty source
    findings = detector.analyze("", "test")
    assert findings == []


def test_detector_short_source():
    """Very short source code should return no findings."""
    detector = VulnerabilityDetector()
    findings = detector.analyze("pragma solidity;", "test")
    assert findings == []
