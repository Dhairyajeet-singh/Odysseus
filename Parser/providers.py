"""LLM provider abstraction.

One interface, three implementations, chosen at runtime:

    OpenAIProvider     real calls, needs OPENAI_API_KEY
    AnthropicProvider  real calls, needs ANTHROPIC_API_KEY
    MockProvider       deterministic canned responses, no key, no network

Two reasons this layer exists rather than calling an SDK inline:

1. It is the "support multiple LLM providers" bonus feature, for free -- the
   rest of the system asks for `provider.complete_json(...)` and never knows or
   cares which model answered.

2. It makes the whole pipeline testable with no API key and no network. The
   mock returns fixed structured output, so every downstream step -- JD parsing,
   evidence extraction, scoring -- can be exercised and asserted in CI. The real
   providers are thin enough that there is little left to go wrong once the mock
   path is proven.

The contract is deliberately narrow: given a system prompt and a user prompt,
return parsed JSON. Structured-JSON output is the only LLM shape this system
needs, so that is the only method the interface exposes.
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional


class LLMError(RuntimeError):
    pass


def _strip_code_fences(text: str) -> str:
    """Models wrap JSON in ```json fences despite being told not to."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _extract_json(text: str) -> Dict[str, Any]:
    """Parse JSON from a model response, tolerating minor sloppiness.

    Falls back to grabbing the outermost {...} span if there is prose around it,
    because 'return only JSON' is a request models honour ~95% of the time, not
    100%.
    """
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError as exc:
                raise LLMError(f"model did not return valid JSON: {exc}") from exc
        raise LLMError("model did not return valid JSON and no object was found")


class LLMProvider(ABC):
    """Return parsed JSON for a (system, user) prompt pair."""

    name: str = "base"

    @abstractmethod
    def complete_json(self, system: str, user: str,
                      temperature: float = 0.0) -> Dict[str, Any]:
        ...


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY not set")

    def complete_json(self, system: str, user: str,
                      temperature: float = 0.0) -> Dict[str, Any]:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMError("pip install openai") from exc
        client = OpenAI(api_key=self.api_key)
        resp = client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return _extract_json(resp.choices[0].message.content or "")


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError("ANTHROPIC_API_KEY not set")

    def complete_json(self, system: str, user: str,
                      temperature: float = 0.0) -> Dict[str, Any]:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("pip install anthropic") from exc
        client = anthropic.Anthropic(api_key=self.api_key)
        # Anthropic has no json_object mode; the instruction to return only JSON
        # lives in the system prompt, and _extract_json cleans up after it.
        resp = client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=temperature,
            system=system + "\n\nReturn ONLY valid JSON. No prose, no code fences.",
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return _extract_json("\n".join(parts))


class MockProvider(LLMProvider):
    """Deterministic provider for tests and offline development.

    Holds a routing function supplied by the caller: given (system, user), it
    returns the canned dict that a real model would plausibly produce. This lets
    each downstream step ship with realistic fixtures and be asserted exactly,
    with no key and no flakiness.
    """
    name = "mock"

    def __init__(self, router: Callable[[str, str], Dict[str, Any]]):
        self._router = router
        self.calls: list = []   # inspectable in tests

    def complete_json(self, system: str, user: str,
                      temperature: float = 0.0) -> Dict[str, Any]:
        self.calls.append({"system": system, "user": user})
        return self._router(system, user)


def get_provider(name: str = "auto", **kwargs) -> LLMProvider:
    """Factory. 'auto' picks whichever key is present in the environment."""
    name = name.lower()
    if name == "openai":
        return OpenAIProvider(**kwargs)
    if name == "anthropic":
        return AnthropicProvider(**kwargs)
    if name == "auto":
        if os.environ.get("OPENAI_API_KEY"):
            return OpenAIProvider(**kwargs)
        if os.environ.get("ANTHROPIC_API_KEY"):
            return AnthropicProvider(**kwargs)
        raise LLMError(
            "no API key found — set OPENAI_API_KEY or ANTHROPIC_API_KEY, "
            "or pass a MockProvider for offline use"
        )
    raise LLMError(f"unknown provider: {name}")
