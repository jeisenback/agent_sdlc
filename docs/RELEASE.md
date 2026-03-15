# Release guide

This repository includes a manual GitHub Actions workflow to perform a TestPyPI publish.

Workflow: `.github/workflows/test-pypi.yml`

Required secrets (add these in the repository Settings → Secrets):
- `TWINE_USERNAME` — your TestPyPI username or API token username
- `TWINE_PASSWORD` — your TestPyPI password or API token

How to run (from the GitHub Actions UI):
1. Go to the repository Actions → "TestPyPI Publish" workflow.
2. Click "Run workflow" and set the `publish` input to `true` to publish the built artifacts to TestPyPI.

Notes:
- The workflow always builds the distribution and uploads the `dist/` artifact. Publishing to TestPyPI is gated on the `publish` input and the `TWINE_*` secrets.
- Use TestPyPI (https://test.pypi.org) for dry-run publishes. For a real PyPI publish you'll need a separate workflow and PyPI credentials — do not store production secrets in this repo unless approved.
