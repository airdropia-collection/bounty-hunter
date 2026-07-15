"""Tests for the secret sanitizer."""
from src.utils.sanitizer import sanitize, is_safe_to_log


_LONG_BLOB = "AAAABBBBCCCCDDDDEEEEFFFFgggghhhhiiiijjjjkkkkllll"


def test_sanitize_email():
    text = "logged in as user@example.com from 1.2.3.4"
    out = sanitize(text)
    assert "user@example.com" not in out


def test_sanitize_long_base64_token():
    text = f"Authorization: Bearer {_LONG_BLOB}"
    out = sanitize(text)
    assert _LONG_BLOB not in out


def test_sanitize_cookie_value():
    text = "Set-Cookie: session=verylongbase64stringvalue_abc123_with_padding"
    out = sanitize(text)
    assert "session=" not in out


def test_sanitize_dict():
    payload = {
        "user": "alice",
        "cookie": "session=verylongbase64stringvalue_abc123",
        "nested": {"token": _LONG_BLOB},
    }
    out = sanitize(payload)
    flat = str(out)
    assert "alice" in flat  # non-secret preserved
    assert "verylongbase64" not in flat
    assert "AAAABBBB" not in flat


def test_sanitize_truncates_long_strings():
    text = "word " * 200  # ~1000 chars with spaces
    out = sanitize(text, max_len=50)
    assert len(out) < 200
    assert "truncated" in out


def test_is_safe_to_log_clean():
    assert is_safe_to_log("Hello world 12345")
    assert is_safe_to_log("normal log message with no secrets")


def test_is_safe_to_log_with_long_token():
    assert not is_safe_to_log(f"my token is {_LONG_BLOB}")


def test_is_safe_to_log_with_email():
    assert not is_safe_to_log("ping me at alice@example.com")


def test_sanitize_exception():
    exc = ValueError(f"auth failed for {_LONG_BLOB}")
    out = sanitize(exc)
    assert "AAAABBBB" not in out


def test_sanitize_preserves_short_strings():
    assert sanitize("hello") == "hello"
    assert sanitize("task_12345") == "task_12345"


def test_sanitize_handles_none_int_bool():
    assert sanitize(None) is None
    assert sanitize(42) == 42
    assert sanitize(True) is True
    assert sanitize(3.14) == 3.14


def test_sanitize_ethereum_address():
    text = "send funds to 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1"
    out = sanitize(text)
    assert "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1" not in out
