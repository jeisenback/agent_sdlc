"""SprintHealthReporter — weekly sprint health digest.

Posts a milestone burn-down table (open blockers, stale issues, % complete)
to a pinned Sprint Health Dashboard issue. No LLM required — gh CLI only.

Local invocation:
    python scripts/run_sprint_health.py --repo owner/repo

Post to the dashboard issue:
    python scripts/run_sprint_health.py --repo owner/repo \\
        --post-comment --health-issue 99
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)

_STALE_DAYS = 7


# ---------------------------------------------------------------------------
# gh CLI helpers
# ---------------------------------------------------------------------------


def _run(cmd: List[str], check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def _check_gh_cli() -> None:
    try:
        result = subprocess.run(
            ["gh", "auth", "status"], capture_output=True, text=True
        )
        if result.returncode != 0:
            print("gh CLI not available or not authenticated", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("gh CLI not available or not authenticated", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


def fetch_milestones(repo: str) -> List[Dict[str, Any]]:
    """Return all open milestones for the repo."""
    raw = _run(
        ["gh", "api", f"repos/{repo}/milestones", "--paginate", "-q", ".[]"],
        check=False,
    )
    if not raw:
        return []
    # gh api --paginate with -q outputs one JSON value per line
    milestones = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            try:
                milestones.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return milestones


def fetch_blocked_issues(repo: str, milestone_title: str) -> List[Dict[str, Any]]:
    """Return open issues with label 'blocked' in the given milestone."""
    raw = _run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--milestone",
            milestone_title,
            "--label",
            "blocked",
            "--state",
            "open",
            "--json",
            "number,title",
            "--limit",
            "100",
        ],
        check=False,
    )
    if not raw:
        return []
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return []


def fetch_open_issues(repo: str, milestone_title: str) -> List[Dict[str, Any]]:
    """Return all open issues in the milestone with updatedAt for stale detection."""
    raw = _run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--milestone",
            milestone_title,
            "--state",
            "open",
            "--json",
            "number,title,updatedAt",
            "--limit",
            "200",
        ],
        check=False,
    )
    if not raw:
        return []
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return []


def identify_stale(
    issues: List[Dict[str, Any]], stale_days: int = _STALE_DAYS
) -> List[Dict[str, Any]]:
    """Return issues not updated within stale_days calendar days."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=stale_days)
    stale = []
    for issue in issues:
        updated_str = issue.get("updatedAt", "")
        if not updated_str:
            continue
        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            if updated < cutoff:
                stale.append(issue)
        except ValueError:
            continue
    return stale


def fetch_repo_owner(repo: str) -> Optional[str]:
    """Return the repo owner login, falling back to env var."""
    try:
        owner = _run(
            ["gh", "api", f"repos/{repo}", "-q", ".owner.login"],
            check=False,
        )
        if owner:
            return owner
    except Exception as exc:
        logger.warning("Could not fetch repo owner: %s", exc)
    return os.environ.get("GITHUB_REPOSITORY_OWNER")


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------


def build_report(
    milestone_rows: List[Dict[str, Any]],
    timestamp: str,
    owner: Optional[str] = None,
) -> str:
    """Build the markdown sprint health report."""
    lines = [
        f"## Sprint Health Dashboard — {timestamp}\n",
        "| Milestone | Total | % Complete | Open Blockers | Stale Issues |",
        "|-----------|-------|------------|---------------|--------------|",
    ]
    blocker_alerts: List[str] = []

    for row in milestone_rows:
        name = row["name"]
        total = row["total"]
        pct = row["pct_complete"]
        blockers = row["blocker_count"]
        stale = row["stale_count"]
        lines.append(f"| {name} | {total} | {pct}% | {blockers} | {stale} |")
        if blockers > 2:
            blocker_alerts.append(name)

    if blocker_alerts:
        tag = f"@{owner}" if owner else "the team"
        lines.append(
            f"\n⚠️ {tag} — the following milestones have >2 open blockers: "
            + ", ".join(f"**{m}**" for m in blocker_alerts)
        )

    return "\n".join(lines)


def collect_milestone_rows(
    repo: str, milestones: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Collect health data for each milestone."""
    rows = []
    for ms in milestones:
        title = ms.get("title", "")
        open_count: int = ms.get("open_issues", 0)
        closed_count: int = ms.get("closed_issues", 0)
        total = open_count + closed_count
        pct = round(closed_count / total * 100) if total > 0 else 0

        blocked = fetch_blocked_issues(repo, title)
        open_issues = fetch_open_issues(repo, title)
        stale = identify_stale(open_issues)

        rows.append(
            {
                "name": title,
                "total": total,
                "pct_complete": pct,
                "blocker_count": len(blocked),
                "stale_count": len(stale),
                "blockers": blocked,
                "stale_issues": stale,
            }
        )
    return rows


def post_comment(repo: str, issue_number: int, body: str) -> None:
    _run(["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", body])
    logger.info("Report posted to issue #%d.", issue_number)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SprintHealthReporter — weekly milestone health digest."
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/repo (default: GITHUB_REPOSITORY env var)",
    )
    parser.add_argument("--post-comment", action="store_true")
    parser.add_argument(
        "--health-issue",
        type=int,
        default=int(os.environ.get("HEALTH_ISSUE_NUMBER", "0")) or None,
        metavar="N",
        help="Issue number for the Sprint Health Dashboard",
    )
    args = parser.parse_args()

    if not args.repo:
        logger.error("--repo or GITHUB_REPOSITORY env var required.")
        return 1

    _check_gh_cli()

    milestones = fetch_milestones(args.repo)
    if not milestones:
        logger.info("No open milestones found for %s.", args.repo)
        milestones = []

    rows = collect_milestone_rows(args.repo, milestones)
    owner = fetch_repo_owner(args.repo)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    report = build_report(rows, timestamp, owner)

    print(report)

    if args.post_comment:
        if not args.health_issue:
            logger.error("--health-issue or HEALTH_ISSUE_NUMBER required to post.")
            return 1
        try:
            post_comment(args.repo, args.health_issue, report)
        except Exception as exc:
            logger.error("Failed to post report: %s", exc)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
