"""NewAgentAgent runner — scaffold a new pattern-compliant agent.

Usage:
    python scripts/run_new_agent.py \\
        --name security_review \\
        --description "Checks for OWASP security issues in diffs" \\
        --rules rules.json \\
        --out ./generated/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)


def _make_provider():
    from agent_sdlc.core.providers import AnthropicProvider, DummyLLMProvider

    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    print("[INFO] No API key — using DummyLLMProvider", file=sys.stderr)
    return DummyLLMProvider()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NewAgentAgent — scaffold a new pattern-compliant agent."
    )
    parser.add_argument("--name", required=True, help="Agent name in snake_case")
    parser.add_argument(
        "--description", required=True, help="What the agent checks and why"
    )
    parser.add_argument(
        "--rules",
        default=None,
        metavar="PATH",
        help="JSON file: [{rule_id, severity, trigger}, ...]",
    )
    parser.add_argument(
        "--input-fields",
        default=None,
        metavar="PATH",
        help="JSON file: [{name, type, required, description}, ...]",
    )
    parser.add_argument(
        "--trigger",
        default="pull_request",
        help="Pipeline trigger key (default: pull_request)",
    )
    parser.add_argument(
        "--out",
        default="./generated",
        metavar="DIR",
        help="Output directory for generated files (default: ./generated)",
    )
    args = parser.parse_args()

    rules = []
    if args.rules:
        try:
            with open(args.rules) as fh:
                rules = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Cannot read rules file: %s", exc)
            return 1

    input_fields = []
    if args.input_fields:
        try:
            with open(args.input_fields) as fh:
                input_fields = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Cannot read input-fields file: %s", exc)
            return 1

    from agent_sdlc.agents.new_agent import NewAgentAgent, NewAgentInput

    provider = _make_provider()
    agent = NewAgentAgent(provider=provider)
    result = agent.run(
        NewAgentInput(
            name=args.name,
            description=args.description,
            rules=rules,
            input_fields=input_fields,
            trigger=args.trigger,
        )
    )

    os.makedirs(args.out, exist_ok=True)
    files = {
        f"agent_sdlc/agents/{args.name}.py": result.agent_source,
        f"scripts/run_{args.name}.py": result.runner_source,
        f"tests/test_{args.name}.py": result.test_source,
        f".agent-pipeline-{args.name}.yml": result.pipeline_entry,
    }
    for rel_path, content in files.items():
        out_path = os.path.join(args.out, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as fh:
            fh.write(content)
        logger.info("Written: %s", out_path)

    if result.review_findings:
        logger.info("Review findings (%d):", len(result.review_findings))
        for f in result.review_findings:
            sev = f.severity.value.upper()
            print(f"  [{sev}] {f.rule}: {f.message}")

    if not result.approved:
        logger.error(
            "NewAgent scaffold FAILED AgentReviewAgent — BLOCKER findings present."
        )
        return 1

    logger.info("NewAgent '%s' scaffold generated and approved.", args.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
