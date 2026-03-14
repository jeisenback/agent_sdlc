# Copilot Usage Instructions for agent_sdlc

Guidance for using GitHub Copilot when working on `agent_sdlc` code.

## Coding style & expectations
- Follow existing project conventions: explicit type hints, Pydantic models for external schemas, and small focused functions.
- Keep functions < 200 lines; prefer composition over inheritance for adapters/providers.

## How to prompt Copilot
- Provide a short docstring and unit test first; let Copilot suggest implementation stubs.
- Example prompt in editor header:
  - `"""Implement SqliteAdapter.execute(sql: str, /) -> int
  Tests: tests/test_sqlite_adapter.py covers basic execute/fetch."""`

## Review generated code
- Always run unit tests after accepting suggestions.
- Verify type hints and Pydantic models; Copilot may omit edge-case validation.

## Security
- Never allow Copilot to inject real API keys or secrets into committed files.

## Running & testing locally
1. Create venv and install deps:
```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
2. Run unit tests:
```bash
pytest -q
```

## When to accept suggestions
- Accept for trivial boilerplate, data classes, and simple helper functions.
- For core interfaces (providers, adapters), prefer manual review and small incremental commits.
