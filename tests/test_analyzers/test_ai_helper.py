"""Tests for the AI helper."""
from src.analyzers.ai_helper import AIHelper


def test_ai_helper_no_keys(monkeypatch):
    """AIHelper should work without any keys (no providers)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    ai = AIHelper()
    assert not ai.has_any_provider
    assert ai.gemini is None
    assert ai.groq is None


def test_ai_helper_init_does_not_crash(monkeypatch):
    """Initialization should never crash even without deps."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    ai = AIHelper()
    # Should not raise
    assert ai is not None


def test_ai_helper_generate_raises_without_providers(monkeypatch):
    """generate() should raise RuntimeError if no providers available."""
    import pytest
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    ai = AIHelper()
    with pytest.raises(RuntimeError, match="All AI providers failed"):
        ai.generate("test prompt", max_retries=1)
