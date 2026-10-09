from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class ProcessMode(StrEnum):
    strict = "strict"  # opt-in only — only marked units enter the pipeline
    scan = "scan"  # rules + keyword on everything, no LLM cost
    auto = "auto"  # full pipeline, ambiguous units reach the LLM (Milestone 2)


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


class UnitResult(BaseModel):
    """Output of one LLM worker call — classification + generated code."""

    role: Role
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reasoning: str
    code_stub: str = ""
    test_stub: str = ""
    open_questions: list[str] = Field(default_factory=list)


class Profile(BaseModel):
    """Per-project calibration profile stored in .tex2code/profile.json."""

    field: str = "unknown"
    subfield: str = ""
    venue_type: str = "preprint"
    education_level: str = "phd"
    audience: str = "labmates"
    code_reader_expertise: str = "reads-python"
    proofs_are_spec: bool = False
    spec_heuristics: list[str] = Field(default_factory=list)
    tone: str = "technical-concise"
    model: str = "claude-sonnet-4-6"
    prior_work_context: str = ""


class ManifestEntry(BaseModel):
    hash: str
    role: Role
    last_processed: str  # ISO date string
    code: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    entries: dict[str, ManifestEntry] = Field(default_factory=dict)
