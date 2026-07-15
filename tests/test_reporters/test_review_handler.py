"""Tests for the review handler."""
from src.reporters.review_handler import ReviewHandler


def test_submit_command():
    h = ReviewHandler()
    result = h.process_comment("/submit", "alice", 42)
    assert result["status"] == "approved"
    assert result["action"] == "submit"
    assert "alice" in result["summary"]


def test_submit_with_note():
    h = ReviewHandler()
    result = h.process_comment("/submit looks solid, verified locally", "bob", 1)
    assert result["status"] == "approved"
    assert result["note"] == "looks solid, verified locally"


def test_reject_command():
    h = ReviewHandler()
    result = h.process_comment("/reject false positive", "carol", 7)
    assert result["status"] == "rejected"
    assert result["action"] == "reject"
    assert "false positive" in result["reason"]


def test_reject_no_reason():
    h = ReviewHandler()
    result = h.process_comment("/reject", "dave", 3)
    assert result["status"] == "rejected"
    assert result["reason"] == "No reason"


def test_modify_command():
    h = ReviewHandler()
    result = h.process_comment("/modify check the transferFrom function", "eve", 9)
    assert result["status"] == "modified"
    assert result["action"] == "modify"
    assert "transferFrom" in result["instructions"]


def test_modify_missing_instructions():
    h = ReviewHandler()
    result = h.process_comment("/modify", "frank", 5)
    assert result["status"] == "error"


def test_resolve_command():
    h = ReviewHandler()
    result = h.process_comment("/resolve fixed", "grace", 11)
    assert result["status"] == "resolved"
    assert result["action"] == "resolve"
    assert "fixed" in result["note"]


def test_unknown_command():
    h = ReviewHandler()
    result = h.process_comment("hello there", "henry", 1)
    assert result["status"] == "ignored"
    assert result["action"] == "noop"


def test_case_insensitive():
    h = ReviewHandler()
    result = h.process_comment("/SUBMIT", "alice", 1)
    assert result["status"] == "approved"
