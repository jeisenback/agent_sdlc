# Contributing to agent_sdlc

Thanks for contributing! This project is designed to be AI-assisted and easy to
bootstrap. This document explains how to set up the dev environment, run tests,
and submit PRs.

Developer setup

1. Bootstrap the project (creates `.venv`, installs dev deps, installs pre-commit hooks, and runs tests):

```bash
python scripts/bootstrap.py
```

2. Activate the venv (if you prefer manual steps):

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

3. Run tests:

```bash
pytest -q
```

Code style

- We use `black`, `isort`, and `ruff` via `pre-commit`. Hooks are configured in `.pre-commit-config.yaml`.
- Run `pre-commit run --all-files` to check formatting locally.

Commit message format

All commit messages must follow the Conventional Commits format:

```
<type>(<scope>): <description>
```

Valid types: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`

Scope is optional. Examples:

```
feat(agents): add IssueRefinementAgent
fix: handle empty diff in PRReviewAgent
chore(ci): pin ruff version
```

A `commit-msg` pre-commit hook enforces this automatically. If your commit is rejected, check the error message for the expected format. The hook runs `scripts/check_commit_msg.sh` which validates against the pattern `^(feat|fix|test|refactor|docs|chore)(\(.+\))?: .+`.

Provider adapters

- Use `DummyLLMProvider` for deterministic tests. Replace the stub classes in
  `agent_sdlc/core/providers.py` with concrete implementations when integrating
  a real provider. Never commit API keys; use environment variables and GitHub
  Secrets for CI.

Pull request workflow

- Create a feature branch off `main`.
- Add tests for new behavior; CI runs unit tests on PRs.
- Keep PRs small and focused; include a short description of the change and any
  migration or compatibility notes.

Security

- Do not add secrets to code or tests. Use environment variables and document any
  required keys in `.env.example` (do not add the `.env` file to the repo).

Questions

If you're unsure about architecture or public API changes, open an issue first
so we can discuss design before implementation.
