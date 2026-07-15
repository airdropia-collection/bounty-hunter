"""Tests for the Telegram notifier."""
from src.utils.telegram import TelegramNotifier


def test_dry_run_when_no_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    tg = TelegramNotifier()
    assert tg._dry_run is True
    assert not tg.is_configured


def test_dry_run_send_returns_false(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    tg = TelegramNotifier()
    assert tg.send("test message") is False


def test_configured_when_credentials_present(monkeypatch):
    """When credentials are present, is_configured should be True even if getMe fails."""
    # getMe will fail (invalid token) but _dry_run should still be False
    # because we don't permanently disable on getMe failure anymore
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "invalid_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    tg = TelegramNotifier()
    # _dry_run is only True if token or chat_id is empty
    # getMe failure doesn't disable — it just logs a warning
    assert tg._dry_run is False  # credentials present, not disabled


def test_send_pipeline_start_dry_run(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    tg = TelegramNotifier()
    # Should not crash
    tg.send_pipeline_start("all", 5)


def test_send_pipeline_complete_dry_run(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    tg = TelegramNotifier()
    tg.send_pipeline_complete(10, 3, 1)


def test_send_finding_dry_run(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    tg = TelegramNotifier()
    tg.send_finding("LayerZero", "Reentrancy", "High", 0.85, "https://example.com")


def test_send_error_dry_run(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    tg = TelegramNotifier()
    tg.send_error("AI failed", context="analyzing LayerZero")


def test_send_operator_needed_dry_run(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    tg = TelegramNotifier()
    tg.send_operator_needed("Missing secret", "https://github.com/...")
