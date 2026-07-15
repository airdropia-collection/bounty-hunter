"""Tests for the doubt reviewer."""
from src.analyzers.doubt_review import DoubtReviewer, ReviewedFinding
from src.analyzers.vuln_detector import Finding


def test_reviewed_finding_creation():
    f = Finding(
        id="test-1",
        title="Test",
        severity="High",
        confidence=0.8,
        description="desc",
        impact="impact",
        recommendation="rec",
    )
    rf = ReviewedFinding(
        original=f,
        survives=True,
        confidence_adjusted=0.7,
        doubts="Minor concerns",
        recommendation="submit",
    )
    assert rf.survives is True
    assert rf.recommendation == "submit"


def test_reviewed_finding_to_dict():
    f = Finding(
        id="x", title="x", severity="Low", confidence=0.3,
        description="", impact="", recommendation="",
    )
    rf = ReviewedFinding(
        original=f, survives=False, confidence_adjusted=0.1,
        doubts="False positive", recommendation="discard",
    )
    d = rf.to_dict()
    assert d["survives"] is False
    assert d["recommendation"] == "discard"
    assert "original" in d


def test_filter_submittable():
    reviewer = DoubtReviewer()

    f1 = Finding(id="1", title="A", severity="High", confidence=0.8,
                 description="", impact="", recommendation="")
    f2 = Finding(id="2", title="B", severity="Low", confidence=0.3,
                 description="", impact="", recommendation="")

    r1 = ReviewedFinding(original=f1, survives=True, confidence_adjusted=0.7,
                         doubts="", recommendation="submit")
    r2 = ReviewedFinding(original=f2, survives=False, confidence_adjusted=0.1,
                         doubts="FP", recommendation="discard")

    submittable = reviewer.filter_submittable([r1, r2])
    assert len(submittable) == 1
    assert submittable[0].original.title == "A"
