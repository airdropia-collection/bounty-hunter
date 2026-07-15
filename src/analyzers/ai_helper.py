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
    # Always try in this order: 3.5-flash → 3.1-flash → 2.5-flash
    # No permanent blacklist — a model that fails on one task may work on the next
    # Minimum model is 2.5-flash (no 2.0 or 1.5 — those are deprecated)
    GEMINI_MODELS = [
        "gemini-3.5-flash",
        "gemini-3.1-flash",
        "gemini-2.5-flash",
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
                self._gemini_model = None  # last successful model (for logging)
                log.info("Gemini client initialized (will try models on each call)")
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
        """Call Gemini, trying models in priority order on EVERY call.

        No permanent blacklist — a model that fails on one task (rate limit,
        network glitch) may work on the next. Always try: 3.5 → 3.1 → 2.5.
        """
        if not self._genai:
            raise RuntimeError("Gemini module not initialized")

        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        kwargs: dict[str, Any] = {"temperature": 0.3, "max_output_tokens": 8192}
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        config = self._genai.GenerationConfig(**kwargs)

        last_error = None
        for model_name in self.GEMINI_MODELS:
            try:
                model = self._genai.GenerativeModel(model_name)
                response = model.generate_content(full_prompt, generation_config=config)
                # Log if model changed from last call
                if self._gemini_model != model_name:
                    self._gemini_model = model_name
                    log.info("Gemini using model: %s", model_name)
                return response.text
            except Exception as exc:
                log.warning("Gemini %s failed: %s", model_name, sanitize(exc))
                last_error = exc
                # Don't blacklist — just try next model

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
