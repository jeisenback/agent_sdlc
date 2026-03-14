from agent_sdlc.core.providers import DummyLLMProvider, ProviderResponse


def test_dummy_provider_default():
    p = DummyLLMProvider()
    r = p.complete("hello")
    assert isinstance(r, ProviderResponse)
    assert r.content == "OK"


def test_dummy_provider_responses():
    p = DummyLLMProvider(responses={"greet": "hi"})
    r = p.complete("greet")
    assert r.content == "hi"


def test_dummy_provider_latency():
    p = DummyLLMProvider(latency=0.01)
    r = p.complete("x")
    assert r.content == "OK"
