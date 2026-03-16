"""AgentReviewAgent runner — individual agent quality gate.

Usage:
    python scripts/run_agent_review.py \\
        --agent-file agent_sdlc/agents/my_agent.py \\
        --test-file tests/test_my_agent.py \\
        [--runner-file scripts/run_my_agent.py]
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
        logger.error("Cannot read file %s: %s", path, exc)
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AgentReviewAgent — individual agent quality gate."
    )
    parser.add_argument("--agent-file", required=True, help="Path to agents/<name>.py")
    parser.add_argument(
        "--test-file", required=True, help="Path to tests/test_<name>.py"
    )
    parser.add_argument(
        "--runner-file", default=None, help="Path to scripts/run_<name>.py"
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Write findings JSON to PATH instead of stdout",
    )
    args = parser.parse_args()

    agent_name = os.path.splitext(os.path.basename(args.agent_file))[0]
    agent_source = _read(args.agent_file)
    test_source = _read(args.test_file)
    runner_source = _read(args.runner_file) if args.runner_file else None

    # Pipeline entry: look up from .agent-pipeline.yml if present
    pipeline_entry: str | None = None
    try:
        with open(".agent-pipeline.yml") as fh:
            content = fh.read()
        if agent_name in content:
            pipeline_entry = f"agent: {agent_name}"
    except OSError:
        pass

    from agent_sdlc.agents.agent_review import AgentReviewAgent, AgentReviewInput

    agent = AgentReviewAgent()
    result = agent.run(
        AgentReviewInput(
            agent_source=agent_source,
            test_source=test_source,
            agent_name=agent_name,
            runner_source=runner_source,
            pipeline_entry=pipeline_entry,
        )
    )

    findings_data = [f.dict() for f in result.findings]

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(findings_data, fh, indent=2)
    else:
        for f in result.findings:
            sev = f.severity.value.upper()
            print(f"[{sev}] {f.rule} @ {f.location}: {f.message}")

    if not result.approved:
        logger.error("AgentReview FAILED — BLOCKER findings present.")
        return 1

    logger.info("AgentReview PASSED for '%s'.", agent_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
