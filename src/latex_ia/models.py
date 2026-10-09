from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class Role(StrEnum):
    context = "context"
    definition = "definition"
    assumption = "assumption"
    spec = "spec"
    result = "result"
    unknown = "unknown"


class Unit(BaseModel):
    """A single parsed unit from the LaTeX document."""

    id: str
    hash: str
    raw: str
    section_path: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    marked: bool = False  # True if wrapped in \begin{tcprocess} or \begin{implement}
    marker_type: str | None = None  # "tcprocess" | "implement" | None


class ClassificationResult(BaseModel):
    unit_id: str
    role: Role
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    tier_used: int  # which gate tier produced this result (-1, 0, 1, 2, 3, 4)
    skipped: bool = False  # True when tier -1 or 0 caused a skip


class ManifestEntry(BaseModel):
    hash: str
    role: Role
    last_processed: str  # ISO date string
    code: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    entries: dict[str, ManifestEntry] = Field(default_factory=dict)
