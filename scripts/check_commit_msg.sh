#!/usr/bin/env bash
# Validates that commit messages follow the Conventional Commits format
# required by this project:  <type>(<scope>): <description>
#
# Valid types: feat, fix, test, refactor, docs, chore
# Scope is optional.  Examples:
#   feat(agents): add IssueRefinementAgent
#   fix: handle empty diff in PRReviewAgent
#   chore(ci): pin ruff version

COMMIT_MSG_FILE="$1"
COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")

PATTERN='^(feat|fix|test|refactor|docs|chore)(\(.+\))?: .+'

if echo "$COMMIT_MSG" | grep -qE "$PATTERN"; then
  exit 0
fi

echo ""
echo "ERROR: Commit message does not follow the required format."
echo ""
echo "  Expected:  <type>(<scope>): <description>"
echo "  Got:       $COMMIT_MSG"
echo ""
echo "  Valid types: feat, fix, test, refactor, docs, chore"
echo "  Scope is optional."
echo ""
echo "  Examples:"
echo "    feat(agents): add IssueRefinementAgent"
echo "    fix: handle empty diff in PRReviewAgent"
echo "    chore(ci): pin ruff version"
echo ""
exit 1
