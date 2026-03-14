# CI Secrets and gating

This file documents the repository secrets used to gate integration and end-to-end
CI jobs and where to configure them.

Secrets used by workflows

- `INTEGRATION_CREDENTIAL` — a secret required for the integration workflow. It can be any
  non-empty secret (e.g., a service account token or a CI-only value). When this secret
  is set in the repository Settings → Secrets, the integration workflow will run automatically
  on schedule or when triggered by other workflows. If it's not set, the job can still be
  run manually via the Actions UI (`Run workflow`).

- `E2E_CREDENTIAL` — a secret required for the e2e workflow. Set this to a CI-only token
  or credential used by end-to-end tests (e.g., a test-host API key or database password).

Adding secrets

1. Go to your repository on GitHub → Settings → Secrets → Actions.
2. Click "New repository secret" and add the secret name and value.

Security notes

- Never add production API keys or credentials to public or fork-accessible repos.
- Prefer creating short-lived tokens or CI-specific service accounts for integration and e2e tests.
