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
from typing import Any, Dict, Optional

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

    def _init_clients(self):
        """Initialize AI clients (lazy imports for optional deps)."""
        # Gemini
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if gemini_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=gemini_key)
                self.gemini = genai.GenerativeModel("gemini-1.5-flash")
                self._genai = genai
                log.info("Gemini client initialized")
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
        return self.gemini is not None or self.groq is not None

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        json_mode: bool = False,
        max_retries: int = 3,
    ) -> str:
        """Generate AI response with fallback chain: Gemini → Groq → error."""
        errors = []

        if self.gemini:
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
        system: Optional[str] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Generate AI response and parse as JSON."""
        result = self.generate(prompt, system, json_mode=True, max_retries=max_retries)
        # Strip markdown code fences if present
        result = result.strip()
        if result.startswith("```"):
            lines = result.split("\n")
            # Remove first and last lines (```json ... ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            result = "\n".join(lines)
        return json.loads(result)

    # ------------------------------------------------------------------ #
    # Provider calls
    # ------------------------------------------------------------------ #
    def _call_gemini(self, prompt: str, system: Optional[str], json_mode: bool) -> str:
        if not self._genai:
            raise RuntimeError("Gemini module not initialized")
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        kwargs: Dict[str, Any] = {"temperature": 0.3, "max_output_tokens": 8192}
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        config = self._genai.GenerationConfig(**kwargs)
        response = self.gemini.generate_content(full_prompt, generation_config=config)
        return response.text

    def _call_groq(self, prompt: str, system: Optional[str], json_mode: bool) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: Dict[str, Any] = {
            "model": "llama-3.1-70b-versatile",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 8192,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.groq.chat.completions.create(**kwargs)
        return response.choices[0].message.content


# Singleton
_ai_helper: Optional[AIHelper] = None


def get_ai_helper() -> AIHelper:
    global _ai_helper
    if _ai_helper is None:
        _ai_helper = AIHelper()
    return _ai_helper
