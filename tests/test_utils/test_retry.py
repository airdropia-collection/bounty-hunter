"""Tests for the retry decorator."""
import pytest

from src.utils.retry import retry_network


def test_retry_succeeds_first_try():
    call_count = 0

    @retry_network(max_attempts=3, base_delay=0.01)
    def success():
        nonlocal call_count
        call_count += 1
        return "ok"

    assert success() == "ok"
    assert call_count == 1


def test_retry_succeeds_after_failures():
    call_count = 0

    @retry_network(max_attempts=3, base_delay=0.01, max_delay=0.05)
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("transient")
        return "ok"

    assert flaky() == "ok"
    assert call_count == 3


def test_retry_exhausts_attempts():
    call_count = 0

    @retry_network(max_attempts=2, base_delay=0.01, max_delay=0.02)
    def always_fail():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("permanent")

    with pytest.raises(RuntimeError, match="permanent"):
        always_fail()
    assert call_count == 2


def test_retry_preserves_return_value():
    @retry_network(max_attempts=3, base_delay=0.01)
    def returns_dict():
        return {"key": "value", "n": 42}

    assert returns_dict() == {"key": "value", "n": 42}
