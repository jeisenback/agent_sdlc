"""IssueLinker runner — enriches findings with related open GitHub issues.

Prerequisite: gh CLI available and authenticated.

Local invocation:
    python scripts/run_issue_linker.py --findings-file findings.json --repo owner/repo
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from typing import Any, Dict, List

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)


def _check_gh_cli() -> None:
    try:
        result = subprocess.run(
            ["gh", "auth", "status"], capture_output=True, text=True
        )
        if result.returncode != 0:
            print("gh CLI not found", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("gh CLI not found", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "IssueLinker — enrich findings with related GitHub issues. "
            "Prerequisite: gh CLI available and authenticated."
        )
    )
    parser.add_argument(
        "--findings-file",
        required=True,
        metavar="PATH",
        help="JSON file containing a list of Finding objects",
    )
    parser.add_argument(
        "--repo",
        required=True,
        metavar="OWNER/REPO",
        help="GitHub repository in owner/repo format",
    )
    args = parser.parse_args()

    _check_gh_cli()

    try:
        with open(args.findings_file) as fh:
            raw: List[Dict[str, Any]] = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Could not read findings file: %s", exc)
        return 1

    from agent_sdlc.agents.issue_linker import IssueLinker, LinkerInput
    from agent_sdlc.core.findings import Finding

    findings = [Finding(**f) for f in raw]
    linker = IssueLinker()
    result = linker.run(LinkerInput(findings=findings, repo=args.repo))

    print(json.dumps([f.dict() for f in result.findings], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
