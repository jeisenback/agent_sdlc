import os
import pytest


def test_openai_provider_optional():
    # Skip if openai SDK not installed or no API key provided
    try:
        import openai  # type: ignore  # noqa: F401
    except Exception:
        pytest.skip("openai SDK not installed")

    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set; skipping live OpenAI test")

    from agent_sdlc.core.openai_provider import OpenAIProviderReal

    provider = OpenAIProviderReal()
    resp = provider.complete("Say hello")
    assert hasattr(resp, "content")
    assert isinstance(resp.content, str)
