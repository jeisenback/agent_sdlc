# Examples — agent_sdlc

This folder contains simple runnable examples showing how to use the example
agents and how to swap LLM providers (dummy vs. real provider adapters).

Run examples from the repository root, preferably after bootstrapping:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python agent_sdlc/examples/pr_review_example.py
python agent_sdlc/examples/issue_refinement_example.py
```

Both examples default to `DummyLLMProvider` so they run offline and deterministically.
To swap to a real provider, replace the provider construction with a concrete
implementation (e.g. `OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])`).
