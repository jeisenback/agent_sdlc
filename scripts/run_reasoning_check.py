"""ReasoningCheckAgent runner — verify BLOCKER findings before they block.

Usage:
    python scripts/run_reasoning_check.py \\
        --findings-file findings.json \\
        --artifact-file diff.txt \\
        --artifact-type diff \\
        --upstream-agent pr_review \\
        --trigger blocker
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


def _read(path: str) -> str:
    try:
        with open(path) as fh:
            return fh.read()
    except OSError as exc:
        logger.error("Cannot read %s: %s", path, exc)
        sys.exit(1)


def _make_provider():
    from agent_sdlc.core.providers import AnthropicProvider, DummyLLMProvider

    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    print("[INFO] No API key — using DummyLLMProvider", file=sys.stderr)
    return DummyLLMProvider()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ReasoningCheckAgent — verify BLOCKER findings before they block CI."
    )
    parser.add_argument("--findings-file", required=True, metavar="PATH")
    parser.add_argument("--artifact-file", required=True, metavar="PATH")
    parser.add_argument(
        "--artifact-type",
        required=True,
        choices=["diff", "issue", "agent_source", "flow"],
    )
    parser.add_argument("--upstream-agent", required=True)
    parser.add_argument(
        "--trigger",
        required=True,
        choices=["blocker", "planning", "error", "miscommunication"],
    )
    parser.add_argument("--out", default=None, metavar="PATH")
    args = parser.parse_args()

    raw_findings = json.loads(_read(args.findings_file))
    artifact = _read(args.artifact_file)

    from agent_sdlc.agents.reasoning_check import (
        ReasoningCheckAgent,
        ReasoningCheckInput,
    )
    from agent_sdlc.core.findings import Finding

    findings = [Finding(**f) for f in raw_findings]
    provider = _make_provider()
    agent = ReasoningCheckAgent(provider=provider)
    result = agent.run(
        ReasoningCheckInput(
            artifact=artifact,
            artifact_type=args.artifact_type,
            upstream_agent=args.upstream_agent,
            findings=findings,
            trigger_reason=args.trigger,
        )
    )

    findings_data = [f.dict() for f in result.verified_findings]
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(findings_data, fh, indent=2)
    else:
        logger.info(
            "Verified: %d  Downgraded: %d  Removed: %d",
            len(result.verified_findings),
            len(result.downgraded),
            len(result.removed),
        )
        for f in result.verified_findings:
            sev = f.severity.value.upper()
            print(f"[{sev}] {f.rule} @ {f.location}: {f.message}")

    return 0 if result.approved else 1


if __name__ == "__main__":
    sys.exit(main())
