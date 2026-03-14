from __future__ import annotations
from typing import Any, Dict, Optional
import os

from .providers import ProviderResponse, ProviderError

try:
    import anthropic  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    anthropic = None  # type: ignore


class AnthropicProviderReal:
    """Optional Anthropic provider adapter.

    Uses the `anthropic` SDK when available. If the package or API key is
    missing the constructor raises `RuntimeError` so callers can fall back to
    `DummyLLMProvider` in tests.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-2.1", **kwargs: Any) -> None:
        if anthropic is None:
            raise RuntimeError("anthropic package is not installed. Install anthropic to use AnthropicProviderReal.")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set and no api_key provided")

        # Create client using common SDK shapes
        if hasattr(anthropic, "Anthropic"):
            self.client = anthropic.Anthropic(api_key=self.api_key)
        elif hasattr(anthropic, "Client"):
            self.client = anthropic.Client(api_key=self.api_key)
        else:
            # Last-resort: use the module as client
            self.client = anthropic

        self.model = model

    def complete(self, prompt: str, **kwargs: Any) -> ProviderResponse:
        try:
            # Newer Anthropic SDKs expose `client.completions.create`
            if hasattr(self.client, "completions"):
                resp = self.client.completions.create(model=self.model, prompt=prompt, **kwargs)
                content = getattr(resp, "completion", None) or (resp.get("completion") if isinstance(resp, dict) else None)
            elif hasattr(self.client, "create_completion"):
                resp = self.client.create_completion(model=self.model, prompt=prompt, **kwargs)
                content = resp["completion"] if isinstance(resp, dict) and "completion" in resp else getattr(resp, "completion", "")
            else:
                # Fallback: attempt to call top-level helper
                resp = self.client.completions.create(model=self.model, prompt=prompt, **kwargs)
                content = getattr(resp, "completion", "") or (resp.get("completion") if isinstance(resp, dict) else "")
        except Exception as e:
            raise ProviderError(f"Anthropic API error: {e}")

        metadata: Dict[str, Any] = {"model": self.model}
        usage = None
        try:
            usage = getattr(resp, "usage", None) or (resp.get("usage") if isinstance(resp, dict) else None)
        except Exception:
            usage = None

        return ProviderResponse(content=content or "", metadata=metadata, usage=usage)
