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
    """When credentials are present, is_configured depends on diagnostic."""
    # Use invalid token — diagnostic will fail → _dry_run = True
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "invalid_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    tg = TelegramNotifier()
    # Diagnostic runs on init and will fail → _dry_run becomes True
    # So is_configured will be False (diagnostic failed)
    assert tg._dry_run is True  # invalid token → dry_run after diagnostic


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
