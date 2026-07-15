"""Tests for the finding verifier (10-step rigorous verification)."""
from src.analyzers.vuln_detector import Finding
from src.analyzers.doubt_review import FindingVerifier, VerifiedFinding


def test_verified_finding_creation():
    f = Finding(
        id="test-1",
        title="Test",
        severity="High",
        confidence=0.8,
        description="desc",
        impact="impact",
        recommendation="rec",
    )
    vf = VerifiedFinding(
        original=f,
        verdict="VERIFIED",
        evidence="Found missing function at line 42",
        inheritance_chain="AgentVault → ReentrancyGuard",
        call_graph="External → buyCollateralPoolTokens → onlyOwner → isOwner (MISSING)",
        falsification_attempts="Checked OpenZeppelin, not found there",
        recommendation="submit",
        confidence_adjusted=0.9,
    )
    assert vf.verdict == "VERIFIED"
    assert vf.recommendation == "submit"


def test_verified_finding_to_dict():
    f = Finding(
        id="x", title="x", severity="Low", confidence=0.3,
        description="", impact="", recommendation="",
    )
    vf = VerifiedFinding(
        original=f, verdict="FALSE_POSITIVE",
        evidence="Function is defined in parent contract",
        inheritance_chain="Resolved",
        call_graph="Resolved",
        falsification_attempts="Found contradicting code at line 15",
        recommendation="discard",
        confidence_adjusted=0.1,
    )
    d = vf.to_dict()
    assert d["verdict"] == "FALSE_POSITIVE"
    assert d["recommendation"] == "discard"
    assert "original" in d
    assert "evidence" in d


def test_filter_submittable():
    verifier = FindingVerifier()

    f1 = Finding(id="1", title="A", severity="High", confidence=0.8,
                 description="", impact="", recommendation="")
    f2 = Finding(id="2", title="B", severity="Low", confidence=0.3,
                 description="", impact="", recommendation="")

    v1 = VerifiedFinding(
        original=f1, verdict="VERIFIED", evidence="evidence",
        inheritance_chain="chain", call_graph="graph",
        falsification_attempts="attempted", recommendation="submit",
        confidence_adjusted=0.9,
    )
    v2 = VerifiedFinding(
        original=f2, verdict="FALSE_POSITIVE", evidence="FP evidence",
        inheritance_chain="chain", call_graph="graph",
        falsification_attempts="attempted", recommendation="discard",
        confidence_adjusted=0.1,
    )

    submittable = verifier.filter_submittable([v1, v2])
    assert len(submittable) == 1
    assert submittable[0].original.title == "A"


def test_filter_worth_reviewing():
    verifier = FindingVerifier()

    f1 = Finding(id="1", title="A", severity="High", confidence=0.8,
                 description="", impact="", recommendation="")
    f2 = Finding(id="2", title="B", severity="Low", confidence=0.3,
                 description="", impact="", recommendation="")
    f3 = Finding(id="3", title="C", severity="Medium", confidence=0.5,
                 description="", impact="", recommendation="")

    v1 = VerifiedFinding(
        original=f1, verdict="VERIFIED", evidence="evidence",
        inheritance_chain="chain", call_graph="graph",
        falsification_attempts="attempted", recommendation="submit",
        confidence_adjusted=0.9,
    )
    v2 = VerifiedFinding(
        original=f2, verdict="FALSE_POSITIVE", evidence="FP",
        inheritance_chain="chain", call_graph="graph",
        falsification_attempts="attempted", recommendation="discard",
        confidence_adjusted=0.1,
    )
    v3 = VerifiedFinding(
        original=f3, verdict="INCONCLUSIVE", evidence="missing source",
        inheritance_chain="chain", call_graph="graph",
        falsification_attempts="attempted", recommendation="investigate",
        confidence_adjusted=0.5,
    )

    worth = verifier.filter_worth_reviewing([v1, v2, v3])
    assert len(worth) == 2  # VERIFIED + INCONCLUSIVE, not FALSE_POSITIVE
    titles = [v.original.title for v in worth]
    assert "A" in titles  # VERIFIED
    assert "C" in titles  # INCONCLUSIVE
    assert "B" not in titles  # FALSE_POSITIVE
