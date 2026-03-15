from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .providers import ProviderError, ProviderResponse

try:
    import openai
except Exception:  # pragma: no cover - optional dependency
    openai = None


class OpenAIProviderReal:  # pragma: no cover
    """Optional OpenAI provider adapter.

    This adapter is lightweight and intentionally tolerant: if the `openai`
    package is not installed, the constructor raises `RuntimeError` so callers
    can fall back to `DummyLLMProvider` in tests.
    """

    def __init__(
        self, api_key: Optional[str] = None, model: str = "gpt-3.5-turbo", **kwargs: Any
    ) -> None:
        if openai is None:
            raise RuntimeError(
                "openai package is not installed. Install openai to use OpenAIProviderReal."
            )
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set and no api_key provided")
        openai.api_key = self.api_key
        self.model = model

    def complete(self, prompt: str, **kwargs: Any) -> ProviderResponse:
        # Prefer ChatCompletion API if available
        try:
            if hasattr(openai, "ChatCompletion"):
                resp = openai.ChatCompletion.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    **kwargs,
                )
                content = resp.choices[0].message.get("content") if resp.choices else ""
            else:
                # Fallback to older Completion API
                resp = openai.Completion.create(
                    model=self.model, prompt=prompt, **kwargs
                )
                content = resp.choices[0].text if resp.choices else ""
        except Exception as e:
            raise ProviderError(f"OpenAI API error: {e}")

        metadata: Dict[str, Any] = {"model": self.model}
        usage: Optional[Dict[str, Any]] = None
        try:
            raw = (
                getattr(resp, "usage", None) or resp.get("usage")
                if isinstance(resp, dict)
                else getattr(resp, "usage", None)
            )
            if isinstance(raw, dict):
                usage = raw
        except Exception:
            usage = None

        return ProviderResponse(content=content, metadata=metadata, usage=usage)
