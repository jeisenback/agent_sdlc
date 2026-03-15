import os
import pytest


def test_anthropic_provider_optional():
    # Skip if anthropic SDK not installed or no API key provided
    try:
        import anthropic  # type: ignore
    except Exception:
        pytest.skip("anthropic SDK not installed")

    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; skipping live Anthropic test")

    from agent_sdlc.core.anthropic_provider import AnthropicProviderReal

    provider = AnthropicProviderReal()
    resp = provider.complete("Say hello")
    assert hasattr(resp, "content")
    assert isinstance(resp.content, str)
