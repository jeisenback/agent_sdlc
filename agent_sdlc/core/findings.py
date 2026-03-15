"""
agent_sdlc/core/findings.py

Shared finding types used by all review and quality-gate agents.

Both the PR Review Agent and the Issue Refinement Agent produce findings
using these types. Centralising them here avoids cross-agent imports and
provides a consistent schema for any future lifecycle automation.

Usage:
    from agent_sdlc.core.findings import Finding, FindingSeverity
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, List
import json

from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    BLOCKER = "blocker"     # Must be resolved before the gated action proceeds
    WARNING = "warning"     # Should be addressed; reviewer judgment required
    SUGGESTION = "suggestion"  # Optional improvement; low priority


class Finding(BaseModel):
    """A portable finding schema used by review and quality-gate agents."""

    location: str = Field(
        default="(unspecified)",
        description="Where the finding applies: file path, field name, or '(diff line)'.",
    )
    line_number: Optional[int] = None
    severity: FindingSeverity = FindingSeverity.WARNING
    rule: str = Field(
        default="general",
        description="Short rule identifier, e.g. 'code:type-hints', 'DoR:ac-count'.",
    )
    message: str
    suggestion: Optional[str] = None


def _make_finding(item: dict) -> Finding:
    """Construct a Finding from a raw dict, compatible with pydantic v1 and v2."""
    if hasattr(Finding, "model_validate"):
        return Finding.model_validate(item)
    return Finding.parse_obj(item)  # type: ignore[attr-defined]


def parse_findings_from_json(text: str) -> List[Finding]:
    """Parse a JSON array of findings into a list of Finding models."""
    payload = json.loads(text)
    return [_make_finding(item) for item in payload]


__all__ = ["Finding", "FindingSeverity", "parse_findings_from_json"]
