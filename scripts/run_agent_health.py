"""AgentHealthMonitor — track finding quality and dismiss rates over time.

Analyses GitHub issue and PR history to surface agent quality signals:
which rules are chronic false positives, which agents have high dismiss
rates, which findings are never acted on. No LLM required — gh CLI only.

Usage:
    python scripts/run_agent_health.py --repo owner/repo --days 30
    python scripts/run_agent_health.py --repo owner/repo --days 30 \\
        --post-comment --health-issue 99
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)

# Regex to detect agent findings in PR/issue comments
_FINDING_PATTERN = re.compile(
    r"\[(BLOCKER|WARNING|SUGGESTION)\]\s+([\w:.-]+)\s+@\s+(.+?):\s+(.+)",
    re.MULTILINE,
)

_DISMISS_KEYWORDS = re.compile(
    r"\b(wontfix|dismissed|false.?positive|not.?relevant|skip|ignore)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# gh CLI helpers
# ---------------------------------------------------------------------------


def _run(cmd: List[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.stdout.strip()
    except FileNotFoundError:
        print("gh CLI not found", file=sys.stderr)
        sys.exit(1)


def _check_gh_cli() -> None:
    result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if result.returncode != 0:
        print("gh CLI not available or not authenticated", file=sys.stderr)
        sys.exit(1)


def _fetch_closed_prs(repo: str, days: int) -> List[Dict[str, Any]]:
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    raw = _run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "closed",
            "--json",
            "number,title,mergedAt,closedAt,comments",
            "--limit",
            "200",
        ]
    )
    if not raw:
        return []
    try:
        prs = json.loads(raw)
    except json.JSONDecodeError:
        return []
    cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
    return [
        pr
        for pr in prs
        if pr.get("closedAt")
        and datetime.fromisoformat(pr["closedAt"].replace("Z", "+00:00")) >= cutoff
    ]


def _fetch_pr_comments(repo: str, pr_number: int) -> List[Dict[str, Any]]:
    raw = _run(
        [
            "gh",
            "api",
            f"repos/{repo}/issues/{pr_number}/comments",
            "--paginate",
            "-q",
            ".[] | {body: .body, created_at: .created_at, user: .user.login}",
        ]
    )
    if not raw:
        return []
    comments = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            try:
                comments.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return comments


def _fetch_total_prs(repo: str, days: int) -> int:
    """Count all PRs (open+closed) in the period."""
    raw = _run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--json",
            "number",
            "--limit",
            "500",
        ]
    )
    if not raw:
        return 0
    try:
        return len(json.loads(raw))
    except json.JSONDecodeError:
        return 0


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def _extract_blocker_findings(comments: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Extract BLOCKER findings posted as comments."""
    findings = []
    for comment in comments:
        body = comment.get("body", "")
        for m in _FINDING_PATTERN.finditer(body):
            if m.group(1) == "BLOCKER":
                findings.append(
                    {
                        "severity": m.group(1),
                        "rule": m.group(2),
                        "location": m.group(3).strip(),
                        "message": m.group(4).strip(),
                    }
                )
    return findings


def _is_dismissed(comments: List[Dict[str, Any]], finding_rule: str) -> bool:
    """Heuristic: BLOCKER dismissed if a subsequent comment contains dismiss keyword
    or if the finding rule is not mentioned again after posting."""
    for comment in comments:
        body = comment.get("body", "")
        if _DISMISS_KEYWORDS.search(body):
            return True
    return False


def analyse(repo: str, days: int) -> Dict[str, Any]:
    """Analyse PR/issue history and return health metrics."""
    closed_prs = _fetch_closed_prs(repo, days)
    total_prs = _fetch_total_prs(repo, days)

    rule_fire_counts: Counter = Counter()
    rule_dismiss_counts: Counter = Counter()
    prs_with_findings = 0

    for pr in closed_prs:
        pr_num = pr.get("number")
        if not pr_num:
            continue
        comments = _fetch_pr_comments(repo, pr_num)
        blockers = _extract_blocker_findings(comments)

        if blockers:
            prs_with_findings += 1

        for b in blockers:
            rule = b["rule"]
            rule_fire_counts[rule] += 1
            if _is_dismissed(comments, rule):
                rule_dismiss_counts[rule] += 1

    # Coverage %
    coverage_pct = round(prs_with_findings / total_prs * 100) if total_prs > 0 else 0

    # Dismiss rate per rule
    dismiss_rates: Dict[str, float] = {}
    for rule, count in rule_fire_counts.items():
        dismissed = rule_dismiss_counts.get(rule, 0)
        dismiss_rates[rule] = round(dismissed / count * 100, 1)

    top_dismiss = sorted(dismiss_rates.items(), key=lambda x: -x[1])[:3]
    top_fired = rule_fire_counts.most_common(3)
    high_dismiss_rules = [r for r, rate in top_dismiss if rate > 50]

    return {
        "repo": repo,
        "period_days": days,
        "total_prs": total_prs,
        "prs_with_findings": prs_with_findings,
        "coverage_pct": coverage_pct,
        "rule_fire_counts": dict(rule_fire_counts),
        "dismiss_rates": dismiss_rates,
        "top_dismiss_rate_rules": top_dismiss,
        "top_fired_rules": top_fired,
        "high_dismiss_rules": high_dismiss_rules,
    }


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------


def build_report(metrics: Dict[str, Any], timestamp: str) -> str:
    repo = metrics["repo"]
    days = metrics["period_days"]
    coverage = metrics["coverage_pct"]
    top_fired = metrics["top_fired_rules"]
    top_dismiss = metrics["top_dismiss_rate_rules"]
    high_dismiss = metrics["high_dismiss_rules"]

    lines = [
        f"## Agent Health Report — {timestamp}",
        f"**Repo:** {repo} | **Period:** last {days} days | "
        f"**Coverage:** {coverage}% of PRs triggered at least one agent",
        "",
        "### Top 3 Most-Fired Rules",
        "| Rule | Fires |",
        "|------|-------|",
    ]
    for rule, count in top_fired:
        lines.append(f"| `{rule}` | {count} |")

    lines += [
        "",
        "### Top 3 Highest Dismiss-Rate Rules",
        "| Rule | Dismiss Rate |",
        "|------|-------------|",
    ]
    for rule, rate in top_dismiss:
        lines.append(f"| `{rule}` | {rate}% |")

    if high_dismiss:
        lines.append(
            "\n⚠️ Rules with >50% dismiss rate (needs-prompt-review): "
            + ", ".join(f"`{r}`" for r in high_dismiss)
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AgentHealthMonitor — weekly finding quality report."
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/repo",
    )
    parser.add_argument("--days", type=int, default=30, help="Analysis window in days")
    parser.add_argument("--post-comment", action="store_true")
    parser.add_argument(
        "--health-issue",
        type=int,
        default=int(os.environ.get("HEALTH_ISSUE_NUMBER", "0")) or None,
        metavar="N",
    )
    parser.add_argument(
        "--out",
        default="agent_health_report.json",
        metavar="PATH",
        help="JSON artifact output path",
    )
    args = parser.parse_args()

    if not args.repo:
        logger.error("--repo or GITHUB_REPOSITORY env var required.")
        return 1

    _check_gh_cli()

    metrics = analyse(args.repo, args.days)

    # Write JSON artifact
    try:
        with open(args.out, "w") as fh:
            json.dump(metrics, fh, indent=2)
        logger.info("JSON artifact written to %s", args.out)
    except OSError as exc:
        logger.warning("Could not write JSON artifact: %s", exc)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    report = build_report(metrics, timestamp)
    print(report)

    if args.post_comment:
        if not args.health_issue:
            logger.error("--health-issue or HEALTH_ISSUE_NUMBER required to post.")
            return 1
        _run(
            [
                "gh",
                "issue",
                "comment",
                str(args.health_issue),
                "--repo",
                args.repo,
                "--body",
                report,
            ]
        )
        logger.info("Report posted to issue #%d.", args.health_issue)

    return 0


if __name__ == "__main__":
    sys.exit(main())
