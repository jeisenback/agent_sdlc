from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass
class ProviderResponse:
    content: str
    metadata: Dict[str, Any] = None
    usage: Dict[str, Any] = None


class ProviderError(Exception):
    pass


class ProviderRateLimitError(ProviderError):
    pass


@runtime_checkable
class ProviderProtocol(Protocol):
    def complete(self, prompt: str, **kwargs) -> ProviderResponse: ...


class DummyLLMProvider:
    """A deterministic, in-process provider useful for unit tests.

    Args:
        responses: optional mapping of prompt -> response string
        default: default response when prompt not found
        latency: artificial latency (seconds) to simulate network calls
    """

    def __init__(
        self,
        responses: Optional[Dict[str, str]] = None,
        default: str = "OK",
        latency: float = 0.0,
    ):
        self.responses = responses or {}
        self.default = default
        self.latency = float(latency)

    def complete(self, prompt: str, **kwargs) -> ProviderResponse:
        if self.latency and self.latency > 0:
            time.sleep(self.latency)
        content = self.responses.get(prompt, self.default)
        metadata = {"prompt": prompt, "timestamp": datetime.utcnow().isoformat()}
        return ProviderResponse(content=content, metadata=metadata)


class OpenAIProvider:
    """Placeholder adapter for OpenAI-like SDKs.

    This class is intentionally a stub so CI/tests do not require the real
    OpenAI SDK. Projects can replace this implementation with a concrete
    adapter that calls the OpenAI APIs and returns a `ProviderResponse`.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def complete(self, prompt: str, **kwargs) -> ProviderResponse:
        raise ProviderError(
            "OpenAIProvider is a stub. Replace with a concrete implementation "
            "that calls the OpenAI SDK or set up a `DummyLLMProvider` for tests."
        )


class AnthropicProvider:
    """Placeholder adapter for Anthropic-like SDKs.

    As with `OpenAIProvider`, this is a non-networking stub. Swap in a real
    provider implementation in production code.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def complete(self, prompt: str, **kwargs) -> ProviderResponse:
        raise ProviderError(
            "AnthropicProvider is a stub. Replace with a concrete implementation "
            "that calls the Anthropic SDK or use `DummyLLMProvider` for tests."
        )
