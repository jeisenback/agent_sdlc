from __future__ import annotations

import os
from typing import Any, Optional

from .providers import ProviderError, ProviderResponse


def _load_anthropic() -> Any:
    try:
        import anthropic

        return anthropic
    except Exception:  # pragma: no cover - optional dependency
        return None


_anthropic: Any = _load_anthropic()


class AnthropicProvider:
    """Concrete Anthropic provider using the messages API (SDK ≥ 0.20).

    Reads ANTHROPIC_API_KEY from the environment when api_key is not supplied.
    Raises RuntimeError at construction time if the SDK or key is missing so
    callers can fall back to DummyLLMProvider.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        if _anthropic is None:
            raise RuntimeError(
                "anthropic package is not installed. Run: pip install anthropic"
            )
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set and no api_key provided.")
        self.client: Any = _anthropic.Anthropic(api_key=self.api_key)
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, prompt: str, **kwargs: Any) -> ProviderResponse:
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise ProviderError(f"Anthropic API error: {exc}") from exc

        # Filter to text blocks only; other block types (tool use, thinking, etc.)
        # do not carry a .text attribute.
        content: str = next((b.text for b in resp.content if hasattr(b, "text")), "")
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        }
        return ProviderResponse(
            content=content, metadata={"model": self.model}, usage=usage
        )


# Keep legacy alias so any existing imports of AnthropicProviderReal still work
AnthropicProviderReal = AnthropicProvider
