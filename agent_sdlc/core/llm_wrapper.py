from __future__ import annotations

from typing import Any, cast

from agent_sdlc.core.providers import ProviderProtocol, ProviderResponse
from agent_sdlc.core.retry import with_retry


class LLMWrapper:
    """Thin wrapper around a ProviderProtocol that adds retry and a small helper.

    The wrapper preserves the ProviderProtocol interface while keeping retry policy
    centralized and tests friendly.
    """

    def __init__(self, provider: ProviderProtocol):
        self.provider = provider

    @with_retry()
    def ask(self, prompt: str, **kwargs: Any) -> ProviderResponse:
        return self.provider.complete(prompt, **kwargs)

    def ask_text(self, prompt: str, **kwargs: Any) -> str:
        return cast(ProviderResponse, self.ask(prompt, **kwargs)).content


__all__ = ["LLMWrapper"]
