"""LLM worker — classify a unit and generate code in a single async call."""

from __future__ import annotations

import json
import re

import litellm

from latex_ia.context import build_context
from latex_ia.models import Profile, Role, Unit, UnitResult

_SYSTEM = """\
You are a scientific code assistant embedded in a LaTeX-to-code pipeline.
Given a unit (section, equation, algorithm, figure, table) from a research paper,
you must:
  1. Classify its role.
  2. If the role is "spec", generate a clean Python implementation and pytest tests.

Respond with a single JSON object — no markdown fences, no extra keys:
{
  "role": "spec" | "definition" | "assumption" | "result" | "context" | "unknown",
  "confidence": <float 0-1>,
  "reasoning": "<one sentence>",
  "code_stub": "<Python source, or empty string>",
  "test_stub": "<pytest source, or empty string>",
  "open_questions": ["<question if something is ambiguous>"]
}

Rules:
- role=spec    → full implementation required; code_stub must be non-empty.
- role=result  → no code; test_stub may contain expected-value assertions.
- other roles  → both stubs empty.
- Use the paper's own symbols as variable names where practical.
- Every generated function must begin with a comment: # spec: <unit_id>
"""

_RE_FENCE = re.compile(r"```(?:json)?\s*")


def _user_prompt(unit: Unit, context: str, profile: Profile) -> str:
    """Build the user-turn prompt from the unit, its context slice, and the profile."""
    section = " > ".join(unit.section_path) if unit.section_path else "unknown section"
    heuristics = ", ".join(profile.spec_heuristics) if profile.spec_heuristics else "none"
    return (
        f"Field: {profile.field} ({profile.subfield})\n"
        f"Education level: {profile.education_level}\n"
        f"Audience: {profile.audience}\n"
        f"Tone: {profile.tone}\n"
        f"Spec heuristics: {heuristics}\n\n"
        f"Section: {section}\n"
        f"Unit ID: {unit.id}\n"
        f"Marked by author: {unit.marked}\n\n"
        f"--- document context ---\n{context}\n--- end context ---\n\n"
        "Classify the TARGET unit and implement it if it is a spec."
    )


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from the response, stripping markdown fences."""
    text = _RE_FENCE.sub("", text).strip().rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
    return json.loads(text[start:end])


async def process_unit(
    unit: Unit,
    all_units: list[Unit],
    profile: Profile,
    *,
    glossary=None,  # Glossary | None — avoids circular import
    _completion=None,
) -> UnitResult:
    """
    Classify *unit* and (if spec) generate code via a single async LLM call.

    *glossary* enriches the context with resolved symbol definitions so the
    LLM receives definitions of symbols used by *unit* even when they appear
    far away in the document.
    *_completion* defaults to litellm.acompletion and is injectable for tests.
    """
    completion = _completion if _completion is not None else litellm.acompletion

    context = build_context(unit, all_units, glossary)
    prompt = _user_prompt(unit, context, profile)

    response = await completion(
        model=profile.model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    raw = response.choices[0].message.content
    data = _extract_json(raw)

    try:
        data["role"] = Role(data.get("role", "unknown"))
    except ValueError:
        data["role"] = Role.unknown
        data["confidence"] = 0.0

    return UnitResult(**data)
