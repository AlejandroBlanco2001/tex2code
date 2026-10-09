from __future__ import annotations

import json
import re

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


def _user_prompt(unit: Unit, context: str, profile: Profile) -> str:
    section = " > ".join(unit.section_path) if unit.section_path else "unknown section"
    heuristics = ", ".join(profile.spec_heuristics) if profile.spec_heuristics else "none"
    return f"""\
Field: {profile.field} ({profile.subfield})
Education level: {profile.education_level}
Audience: {profile.audience}
Tone: {profile.tone}
Spec heuristics: {heuristics}

Section: {section}
Unit ID: {unit.id}
Marked by author: {unit.marked}

--- document context ---
{context}
--- end context ---

Classify the TARGET unit and implement it if it is a spec.
"""


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from the response, stripping markdown fences."""
    # Strip ```json ... ``` fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # Find the first { ... } block
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
    return json.loads(text[start:end])


def process_unit(
    unit: Unit,
    all_units: list[Unit],
    profile: Profile,
    *,
    _completion=None,  # injectable for tests
) -> UnitResult:
    """
    Call the LLM to classify and (if spec) implement a single unit.

    _completion is the litellm.completion callable; pass a mock in tests.
    """
    if _completion is None:
        import litellm

        _completion = litellm.completion

    context = build_context(unit, all_units)
    prompt = _user_prompt(unit, context, profile)

    response = _completion(
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

    # Ensure role is a valid Role value; default to unknown on bad data
    try:
        data["role"] = Role(data.get("role", "unknown"))
    except ValueError:
        data["role"] = Role.unknown
        data["confidence"] = 0.0

    return UnitResult(**data)
