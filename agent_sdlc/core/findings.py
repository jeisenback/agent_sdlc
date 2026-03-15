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

import json
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    BLOCKER = "blocker"  # Must be resolved before the gated action proceeds
    WARNING = "warning"  # Should be addressed; reviewer judgment required
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


def _make_finding(item: Dict[str, Any]) -> Finding:
    """Construct a Finding from a raw dict, compatible with pydantic v1 and v2."""
    if hasattr(Finding, "model_validate"):
        return Finding.model_validate(item)
    return Finding(**item)  # pydantic v1 compat


def parse_findings_from_json(text: str) -> List[Finding]:
    """Parse a JSON array of findings into a list of Finding models.

    Strips markdown code fences (```json ... ``` or ``` ... ```) before
    parsing so the function is robust to LLM responses that wrap JSON.
    """
    # Strip markdown code fences if present
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # drop opening fence line and closing fence line
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        stripped = "\n".join(inner).strip()

    # Extract the outermost JSON array using bracket-depth matching so that
    # ']' characters inside string values do not truncate the array early.
    start = stripped.find("[")
    if start != -1:
        depth = 0
        in_string = False
        escape_next = False
        end = -1
        for i, ch in enumerate(stripped[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            stripped = stripped[start : end + 1]

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        # Last-resort: the model produced invalid JSON (e.g. unescaped inner quotes).
        # Extract individual objects with a regex so we get partial results rather
        # than crashing entirely.
        import logging
        import re

        logging.getLogger(__name__).warning(
            "parse_findings_from_json: strict JSON parse failed; attempting object extraction."
        )
        # Pull out each {...} block that has at least a "severity" key
        raw_objects = re.findall(r"\{[^{}]+\}", stripped)
        payload = []
        for obj in raw_objects:
            try:
                payload.append(json.loads(obj))
            except json.JSONDecodeError:
                continue
        if not payload:
            return []
    return [_make_finding(item) for item in payload]


__all__ = ["Finding", "FindingSeverity", "parse_findings_from_json"]
