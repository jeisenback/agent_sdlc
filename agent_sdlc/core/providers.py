from __future__ import annotations
from typing import Protocol, Any, Dict, Optional, runtime_checkable
from dataclasses import dataclass
from datetime import datetime
import time


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

    def __init__(self, responses: Optional[Dict[str, str]] = None, default: str = "OK", latency: float = 0.0):
        self.responses = responses or {}
        self.default = default
        self.latency = float(latency)

    def complete(self, prompt: str, **kwargs) -> ProviderResponse:
        if self.latency and self.latency > 0:
            time.sleep(self.latency)
        content = self.responses.get(prompt, self.default)
        metadata = {"prompt": prompt, "timestamp": datetime.utcnow().isoformat()}
        return ProviderResponse(content=content, metadata=metadata)
