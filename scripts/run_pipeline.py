"""Pipeline Orchestrator — YAML-driven agent pipeline runner.

Reads .agent-pipeline.yml, executes declared agent sequences, collects
findings via FindingAggregator, and prints a unified report.

Usage:
    python scripts/run_pipeline.py --trigger pull_request --pr 42
    python scripts/run_pipeline.py --trigger issues_opened --issue 7
    python scripts/run_pipeline.py --trigger issues_labeled_bug --issue 7
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import yaml  # pyyaml

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)

# Map agent logical name → runner script path
_AGENT_RUNNERS: Dict[str, str] = {
    "pr_review": "scripts/run_pr_review.py",
    "issue_refinement": "scripts/run_issue_refinement.py",
    "process_gap": "scripts/run_process_gap.py",
    "issue_linker": "scripts/run_issue_linker.py",
    "sprint_health": "scripts/run_sprint_health.py",
    "finding_aggregator": "scripts/run_finding_aggregator.py",
    "product_owner": "scripts/run_product_owner.py",
    "ux_review": "scripts/run_ux_review.py",
    "ui_design": "scripts/run_ui_design.py",
    "traceability": "scripts/run_traceability.py",
    "diagram": "scripts/run_diagram.py",
    "prompt_review": "scripts/run_prompt_review.py",
    "arch_review": "scripts/run_arch_review.py",
    "assumption_checker": "scripts/run_assumption_checker.py",
    "rca": "scripts/run_rca.py",
}


# ---------------------------------------------------------------------------
# Paths filter
# ---------------------------------------------------------------------------


def _get_changed_files(pr_number: Optional[int]) -> List[str]:
    """Return list of changed files for the given PR (best-effort)."""
    if not pr_number:
        return []
    try:
        raw = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--json",
                "files",
                "-q",
                ".files[].path",
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        return [line for line in raw.splitlines() if line]
    except FileNotFoundError:
        return []


def _paths_match(patterns: List[str], changed_files: List[str]) -> bool:
    """Return True if any changed file matches any pattern."""
    if not changed_files:
        # No changed-files info available — don't skip
        return True
    for pattern in patterns:
        for path in changed_files:
            if fnmatch.fnmatch(path, pattern):
                return True
    return False


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------


def _build_cmd(
    agent_cfg: Dict[str, Any],
    pr_number: Optional[int],
    issue_number: Optional[int],
    out_file: str,
) -> Optional[List[str]]:
    """Build the subprocess command for an agent step."""
    agent_name = agent_cfg.get("agent", "")
    runner = _AGENT_RUNNERS.get(agent_name)
    if not runner:
        logger.warning("No runner registered for agent '%s' — skipping", agent_name)
        return None
    if not os.path.exists(runner):
        logger.warning(
            "Runner '%s' not found — skipping agent '%s'", runner, agent_name
        )
        return None

    cmd = [sys.executable, runner, "--out", out_file]
    if pr_number is not None:
        cmd += ["--pr", str(pr_number)]
    if issue_number is not None:
        cmd += ["--issue", str(issue_number)]
    # Forward extra config keys as flags
    if "mode" in agent_cfg:
        cmd += ["--mode", agent_cfg["mode"]]
    if "type" in agent_cfg:
        cmd += ["--type", agent_cfg["type"]]
    return cmd


def _run_agent(
    agent_cfg: Dict[str, Any],
    pr_number: Optional[int],
    issue_number: Optional[int],
    changed_files: List[str],
) -> Tuple[str, bool, List[Any]]:
    """Run a single agent. Returns (agent_name, success, findings)."""
    agent_name = agent_cfg.get("agent", "unknown")

    # paths filter
    paths = agent_cfg.get("paths", [])
    if paths and not _paths_match(paths, changed_files):
        logger.info("Agent '%s' skipped — no matching files changed", agent_name)
        return agent_name, True, []

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
        out_file = tmp.name

    try:
        cmd = _build_cmd(agent_cfg, pr_number, issue_number, out_file)
        if cmd is None:
            return agent_name, True, []

        logger.info("Running agent '%s': %s", agent_name, " ".join(cmd))
        env = {**os.environ, "PYTHONPATH": os.getcwd()}
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if result.returncode not in (0, 1):
            logger.warning(
                "Agent '%s' exited with code %d:\n%s",
                agent_name,
                result.returncode,
                result.stderr,
            )
            return agent_name, False, []

        try:
            with open(out_file) as fh:
                findings = json.load(fh)
        except (OSError, json.JSONDecodeError):
            findings = []

        return agent_name, True, findings

    finally:
        try:
            os.unlink(out_file)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------


def _execute_step(
    step: Dict[str, Any],
    pr_number: Optional[int],
    issue_number: Optional[int],
    changed_files: List[str],
) -> Tuple[bool, Dict[str, List[Any]]]:
    """Execute one step (parallel / sequential / always).
    Returns (should_abort, {agent_name: findings})."""
    all_findings: Dict[str, List[Any]] = {}

    if "parallel" in step:
        agents = step["parallel"]
        with ThreadPoolExecutor() as pool:
            futures = {
                pool.submit(
                    _run_agent, cfg, pr_number, issue_number, changed_files
                ): cfg
                for cfg in agents
            }
            for fut in as_completed(futures):
                agent_cfg = futures[fut]
                name, success, findings = fut.result()
                all_findings[name] = findings
                if not success and agent_cfg.get("on_failure") == "abort":
                    return True, all_findings

    elif "sequential" in step or "always" in step:
        agents = step.get("sequential") or step.get("always")
        for agent_cfg in agents:
            name, success, findings = _run_agent(
                agent_cfg, pr_number, issue_number, changed_files
            )
            all_findings[name] = findings
            if not success and agent_cfg.get("on_failure") == "abort":
                return True, all_findings

    return False, all_findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def load_pipeline_config(path: str = ".agent-pipeline.yml") -> Dict[str, Any]:
    with open(path) as fh:
        return yaml.safe_load(fh)  # type: ignore[no-any-return]


def run_pipeline(
    trigger: str,
    pr_number: Optional[int] = None,
    issue_number: Optional[int] = None,
    config_path: str = ".agent-pipeline.yml",
) -> Tuple[bool, Dict[str, List[Any]]]:
    """Execute the pipeline for the given trigger.

    Returns (aborted, all_findings_by_agent).
    """
    config = load_pipeline_config(config_path)
    pipelines = config.get("pipelines", {})
    pipeline = pipelines.get(trigger)
    if not pipeline:
        logger.warning("No pipeline configured for trigger '%s'", trigger)
        return False, {}

    changed_files = _get_changed_files(pr_number)
    all_findings: Dict[str, List[Any]] = {}
    steps = pipeline.get("steps", [])

    for step in steps:
        aborted, step_findings = _execute_step(
            step, pr_number, issue_number, changed_files
        )
        all_findings.update(step_findings)
        if aborted:
            logger.warning("Pipeline aborted at step due to on_failure=abort")
            return True, all_findings

    return False, all_findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pipeline Orchestrator — YAML-driven agent pipeline runner."
    )
    parser.add_argument(
        "--trigger",
        required=True,
        choices=["pull_request", "issues_opened", "issues_labeled_bug"],
        help="Pipeline trigger to execute",
    )
    parser.add_argument("--pr", type=int, default=None, help="PR number")
    parser.add_argument("--issue", type=int, default=None, help="Issue number")
    parser.add_argument(
        "--config",
        default=".agent-pipeline.yml",
        help="Path to pipeline config YAML",
    )
    args = parser.parse_args()

    aborted, findings_by_agent = run_pipeline(
        trigger=args.trigger,
        pr_number=args.pr,
        issue_number=args.issue,
        config_path=args.config,
    )

    total = sum(len(v) for v in findings_by_agent.values())
    logger.info(
        "Pipeline %s — %d agents ran, %d findings total",
        "ABORTED" if aborted else "COMPLETE",
        len(findings_by_agent),
        total,
    )

    for agent_name, findings in findings_by_agent.items():
        for f in findings:
            sev = f.get("severity", "unknown").upper()
            rule = f.get("rule", "?")
            loc = f.get("location", "?")
            msg = f.get("message", "")
            print(f"[{sev}] {rule} @ {loc}: {msg}")

    return 1 if aborted else 0


if __name__ == "__main__":
    sys.exit(main())
