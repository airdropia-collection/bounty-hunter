"""Tests for the config module."""

from src.config import Config


def test_default_config_has_no_secrets(monkeypatch):
    # Clear all env vars
    for key in ["GEMINI_API_KEY", "GROQ_API_KEY", "GH_PAT", "GH_REPO"]:
        monkeypatch.delenv(key, raising=False)
    cfg = Config()  # create AFTER clearing env
    assert cfg.GEMINI_API_KEY == ""
    assert cfg.GROQ_API_KEY == ""
    assert not cfg.has_gemini
    assert not cfg.has_groq
    assert not cfg.has_any_llm
    assert not cfg.has_github


def test_gemini_key_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    cfg = Config()
    assert cfg.has_gemini
    assert cfg.has_any_llm


def test_groq_key_present(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg = Config()
    assert cfg.has_groq
    assert cfg.has_any_llm


def test_github_creds(monkeypatch):
    monkeypatch.setenv("GH_PAT", "ghp_FAKE_TOKEN_PLACEHOLDER")
    monkeypatch.setenv("GH_REPO", "test/repo")
    cfg = Config()
    assert cfg.has_github
    assert cfg.GH_REPO == "test/repo"


def test_missing_critical_secrets(monkeypatch):
    for key in ["GEMINI_API_KEY", "GROQ_API_KEY", "GH_PAT", "GH_REPO"]:
        monkeypatch.delenv(key, raising=False)
    cfg = Config()
    missing = cfg.missing_critical_secrets()
    assert "GEMINI_API_KEY" in missing
    assert "GROQ_API_KEY" in missing
    assert "GH_PAT + GH_REPO" in missing


def test_missing_critical_secrets_when_all_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    monkeypatch.setenv("GROQ_API_KEY", "k2")
    monkeypatch.setenv("GH_PAT", "k3")
    monkeypatch.setenv("GH_REPO", "test/repo")
    cfg = Config()
    assert cfg.missing_critical_secrets() == []


def test_dry_run_default_true(monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    cfg = Config()
    assert cfg.DRY_RUN is True


def test_dry_run_false(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    cfg = Config()
    assert cfg.DRY_RUN is False


def test_dry_run_various_values(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    assert Config().DRY_RUN is True
    monkeypatch.setenv("DRY_RUN", "TRUE")
    assert Config().DRY_RUN is True
    monkeypatch.setenv("DRY_RUN", "false")
    assert Config().DRY_RUN is False
    monkeypatch.setenv("DRY_RUN", "anything_else")
    assert Config().DRY_RUN is False


def test_optional_secrets_missing(monkeypatch):
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    monkeypatch.delenv("WALLET_ADDRESS", raising=False)
    cfg = Config()
    missing = cfg.missing_optional_secrets()
    assert any("ETHERSCAN" in m for m in missing)
    assert any("WALLET" in m for m in missing)


def test_optional_secrets_present(monkeypatch):
    monkeypatch.setenv("ETHERSCAN_API_KEY", "k")
    monkeypatch.setenv("WALLET_ADDRESS", "0xabc")
    cfg = Config()
    assert cfg.missing_optional_secrets() == []
