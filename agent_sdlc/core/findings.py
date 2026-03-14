from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from typing import Any
import json

# `parse_raw_as` existed in pydantic v1 but was removed in v2; import if available
try:
    from pydantic import parse_raw_as  # type: ignore
except Exception:
    parse_raw_as = None


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Finding(BaseModel):
    """A portable finding schema used by agents and tests.

    This model includes the simple fields expected by the unit tests
    (`id`, `title`, `description`, `severity`, `tags`) and a few optional
    fields useful for richer integrations (`location`, `line_number`).
    """

    id: Optional[str] = None
    title: str
    description: str
    severity: Severity = Severity.MEDIUM
    tags: List[str] = Field(default_factory=list)

    # Optional extras for richer consumers
    location: Optional[str] = None
    line_number: Optional[int] = None
    suggestion: Optional[str] = None


__all__ = ["Finding", "Severity"]


def _make_finding(item: Any) -> Finding:
    """Construct a `Finding` from a mapping, compatible with pydantic v1 and v2.

    Usage: prefer `parse_raw_as(List[Finding], text)` for raw JSON, but fall back
    to this helper when that isn't available or fails.
    """
    if hasattr(Finding, "model_validate"):
        return Finding.model_validate(item)
    return Finding.parse_obj(item)


def parse_findings_from_json(text: str) -> list[Finding]:
    """Parse a JSON array of findings into a list of `Finding` models.

    Tries `pydantic.parse_raw_as(List[Finding], ...)` first for v1/v2 compatibility
    and falls back to `json.loads` + `_make_finding` when needed.
    """
    if parse_raw_as is not None:
        try:
            return parse_raw_as(list[Finding], text)
        except Exception:
            pass
    payload = json.loads(text)
    return [_make_finding(item) for item in payload]
