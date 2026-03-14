from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


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
