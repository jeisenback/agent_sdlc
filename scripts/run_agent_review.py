"""AgentReviewAgent runner — individual and system quality gate.

Usage (individual mode):
    python scripts/run_agent_review.py \\
        --agent-file agent_sdlc/agents/my_agent.py \\
        --test-file tests/test_my_agent.py \\
        [--runner-file scripts/run_my_agent.py]

Usage (system mode — auto-discovers all agents):
    python scripts/run_agent_review.py --mode system
"""

from __future__ import annotations

import argparse
import glob
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


def _read_opt(path: str) -> str:
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return ""


def _run_individual(args) -> int:
    from agent_sdlc.agents.agent_review import AgentReviewAgent, AgentReviewInput

    agent_name = os.path.splitext(os.path.basename(args.agent_file))[0]
    agent_source = _read(args.agent_file)
    test_source = _read(args.test_file)
    runner_source = _read(args.runner_file) if args.runner_file else None

    pipeline_entry: str | None = None
    try:
        with open(".agent-pipeline.yml") as fh:
            content = fh.read()
        if agent_name in content:
            pipeline_entry = f"agent: {agent_name}"
    except OSError:
        pass

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
    return _output(result, args.out)


def _run_system(args) -> int:
    from agent_sdlc.agents.agent_review import AgentReviewAgent, SystemReviewInput

    agent_sources = {}
    for path in glob.glob("agent_sdlc/agents/*.py"):
        name = os.path.splitext(os.path.basename(path))[0]
        if name == "__init__":
            continue
        source = _read_opt(path)
        if source:
            agent_sources[name] = source

    pipeline_config = _read_opt(".agent-pipeline.yml")

    namespaces = []
    import re

    for source in agent_sources.values():
        namespaces += re.findall(r"['\"]([A-Za-z][A-Za-z0-9_-]+):", source)

    agent = AgentReviewAgent()
    result = agent.run_system(
        SystemReviewInput(
            agent_sources=agent_sources,
            pipeline_config=pipeline_config,
            finding_namespaces=list(set(namespaces)),
        )
    )
    return _output(result, args.out)


def _output(result, out_path) -> int:
    from agent_sdlc.agents.agent_review import AgentReviewResult

    assert isinstance(result, AgentReviewResult)
    findings_data = [f.dict() for f in result.findings]

    if out_path:
        with open(out_path, "w") as fh:
            json.dump(findings_data, fh, indent=2)
    else:
        for f in result.findings:
            sev = f.severity.value.upper()
            print(f"[{sev}] {f.rule} @ {f.location}: {f.message}")

    if not result.approved:
        logger.error("AgentReview FAILED — BLOCKER findings present.")
        return 1

    logger.info("AgentReview PASSED.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AgentReviewAgent — individual and system quality gate."
    )
    parser.add_argument(
        "--mode",
        choices=["individual", "system"],
        default="individual",
        help="Review mode (default: individual)",
    )
    parser.add_argument(
        "--agent-file", default=None, help="Path to agents/<name>.py (individual mode)"
    )
    parser.add_argument(
        "--test-file",
        default=None,
        help="Path to tests/test_<name>.py (individual mode)",
    )
    parser.add_argument(
        "--runner-file",
        default=None,
        help="Path to scripts/run_<name>.py (individual mode)",
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Write findings JSON to PATH instead of stdout",
    )
    args = parser.parse_args()

    if args.mode == "system":
        return _run_system(args)

    # individual mode
    if not args.agent_file or not args.test_file:
        logger.error("--agent-file and --test-file are required for individual mode.")
        return 1
    return _run_individual(args)


if __name__ == "__main__":
    sys.exit(main())
