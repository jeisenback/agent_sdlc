# Providers & Adapters

Use `agent_sdlc.core.providers.DummyLLMProvider` for deterministic local tests.

The repo also includes optional, SDK-backed adapters:

- `agent_sdlc.core.openai_provider.OpenAIProviderReal` (requires `openai` and `OPENAI_API_KEY`)
- `agent_sdlc.core.anthropic_provider.AnthropicProviderReal` (requires `anthropic` and `ANTHROPIC_API_KEY`)

DB adapters:

- `agent_sdlc.core.db.SqliteAdapter` — default for unit tests
- `agent_sdlc.core.sqlalchemy_adapter.SqlAlchemyAdapter` — optional SQLAlchemy-based adapter for integration tests

Environment variables:

- `OPENAI_API_KEY` — API key for OpenAI provider (optional)
- `ANTHROPIC_API_KEY` — API key for Anthropic provider (optional)
