"""
AI Helper — Gemini → Groq fallback chain.

Uses Google Gemini (1M tokens/day free) as primary AI provider,
with Groq (Llama-3.1-70B, 1M tokens/day free) as fallback.

Both providers are lazily imported so the module works even if
optional dependencies are not installed (e.g., in test environments).

Usage:
    from src.analyzers.ai_helper import get_ai_helper
    ai = get_ai_helper()
    response = ai.generate(
        prompt="Analyze this Solidity code for vulnerabilities...",
        system="You are a smart contract security auditor.",
    )
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from src.utils.logger import get_logger
from src.utils.sanitizer import sanitize

log = get_logger("ai")


class AIHelper:
    """Multi-provider free AI helper with automatic fallback."""

    def __init__(self):
        self.gemini = None
        self.groq = None
        self._genai = None  # cached google.generativeai module
        self._init_clients()

    # Gemini model priority (user-confirmed):
    # 3.5-flash → 3.1-flash → 2.5-flash (all have 1M tok/day free)
    # 2.0-flash and 1.5-flash as last-resort fallbacks
    GEMINI_MODELS = [
        "gemini-3.5-flash",
        "gemini-3.1-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
    ]

    def _init_clients(self):
        """Initialize AI clients (lazy imports for optional deps)."""
        # Gemini
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if gemini_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=gemini_key)
                self._genai = genai
                # Don't pick a model yet — we'll try each on first call
                # and remember which one works
                self._gemini_model = None
                self._gemini_failed_models: set = set()
                log.info("Gemini client initialized (will try models on first call)")
            except ImportError:
                log.warning("google-generativeai not installed; Gemini disabled")
            except Exception as exc:
                log.error("Gemini init failed: %s", sanitize(exc))

        # Groq (via OpenAI-compatible API)
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                from openai import OpenAI

                self.groq = OpenAI(
                    api_key=groq_key,
                    base_url="https://api.groq.com/openai/v1",
                )
                log.info("Groq client initialized")
            except ImportError:
                log.warning("openai not installed; Groq disabled")
            except Exception as exc:
                log.error("Groq init failed: %s", sanitize(exc))

    @property
    def has_any_provider(self) -> bool:
        return self._genai is not None or self.groq is not None

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        json_mode: bool = False,
        max_retries: int = 3,
    ) -> str:
        """Generate AI response with fallback chain: Gemini → Groq → error."""
        errors = []

        if self._genai:
            for attempt in range(max_retries):
                try:
                    return self._call_gemini(prompt, system, json_mode)
                except Exception as exc:
                    err = f"Gemini attempt {attempt + 1}: {sanitize(exc)}"
                    errors.append(err)
                    log.warning("%s", err)
                    time.sleep(2 ** attempt)

        if self.groq:
            for attempt in range(max_retries):
                try:
                    return self._call_groq(prompt, system, json_mode)
                except Exception as exc:
                    err = f"Groq attempt {attempt + 1}: {sanitize(exc)}"
                    errors.append(err)
                    log.warning("%s", err)
                    time.sleep(2 ** attempt)

        raise RuntimeError(f"All AI providers failed: {'; '.join(errors)}")

    def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Generate AI response and parse as JSON."""
        result = self.generate(prompt, system, json_mode=True, max_retries=max_retries)
        # Strip markdown code fences if present
        result = result.strip()
        if result.startswith("```"):
            lines = result.split("\n")
            # Remove first and last lines (```json ... ```)
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            result = "\n".join(lines)
        return json.loads(result)

    # ------------------------------------------------------------------ #
    # Provider calls
    # ------------------------------------------------------------------ #
    def _call_gemini(self, prompt: str, system: str | None, json_mode: bool) -> str:
        """Call Gemini, trying multiple models if one fails.

        If we already found a working model, use it directly.
        If not, try each model in priority order until one works.
        Models that return 404 (not found) or 429 (quota=0) are
        remembered as failed so we don't retry them.
        """
        if not self._genai:
            raise RuntimeError("Gemini module not initialized")

        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        kwargs: dict[str, Any] = {"temperature": 0.3, "max_output_tokens": 8192}
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        config = self._genai.GenerationConfig(**kwargs)

        # If we already have a working model, try it first
        models_to_try = []
        if self._gemini_model and self._gemini_model not in self._gemini_failed_models:
            models_to_try.append(self._gemini_model)
        # Add remaining models that haven't failed
        for m in self.GEMINI_MODELS:
            if m not in models_to_try and m not in self._gemini_failed_models:
                models_to_try.append(m)

        last_error = None
        for model_name in models_to_try:
            try:
                model = self._genai.GenerativeModel(model_name)
                response = model.generate_content(full_prompt, generation_config=config)
                # Success! Remember this model for future calls
                if self._gemini_model != model_name:
                    self._gemini_model = model_name
                    log.info("Gemini using model: %s", model_name)
                return response.text
            except Exception as exc:
                err_str = str(exc)
                # 404 = model not found, 429 = quota exceeded
                # Mark these models as permanently failed for this session
                if "404" in err_str or "not found" in err_str.lower():
                    self._gemini_failed_models.add(model_name)
                    log.warning("Gemini model %s not available, trying next", model_name)
                elif "429" in err_str and "limit: 0" in err_str:
                    self._gemini_failed_models.add(model_name)
                    log.warning("Gemini model %s has quota=0, trying next", model_name)
                else:
                    # Transient error (rate limit, network) — don't mark as failed
                    log.warning("Gemini model %s error: %s", model_name, sanitize(exc))
                last_error = exc

        raise RuntimeError(f"All Gemini models failed. Last error: {sanitize(last_error)}")

    def _call_groq(self, prompt: str, system: str | None, json_mode: bool) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": "llama-3.3-70b-versatile",  # updated from 3.1 (deprecated)
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 8192,
        }
        # Groq requires the word "json" in the prompt when using response_format
        if json_mode and "json" in prompt.lower():
            kwargs["response_format"] = {"type": "json_object"}
        elif json_mode:
            # Add instruction to return JSON
            messages[-1]["content"] += "\n\nReturn ONLY valid JSON, no markdown fences."

        response = self.groq.chat.completions.create(**kwargs)
        return response.choices[0].message.content


# Singleton
_ai_helper: AIHelper | None = None


def get_ai_helper() -> AIHelper:
    global _ai_helper
    if _ai_helper is None:
        _ai_helper = AIHelper()
    return _ai_helper
