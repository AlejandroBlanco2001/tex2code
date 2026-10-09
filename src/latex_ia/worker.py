"""LLM worker — classify, test-first, then implement."""

from __future__ import annotations

import json
import re

import litellm

from latex_ia.context import build_context
from latex_ia.models import Profile, Role, Unit, UnitResult

# Pass 1: classify the unit and generate tests.
# Code is deliberately excluded — the test stub becomes the contract for pass 2.
_SYSTEM_TEST = """\
You are a scientific code assistant analyzing a unit from a research paper.

Step 1 — Classify the unit role.
Step 2 — If role is "spec", write pytest tests that encode the mathematical specification.

Naming rules:
- Use the paper's own terminology for the function name
  (e.g. "scaled_dot_product_attention", "feed_forward_network", "elbo_lower_bound").
- If you must infer the name from context (no explicit label in the paper), use your
  best guess and add this comment on the line above the function:
  # TODO: rename — inferred from context

Test rules:
- Include all necessary imports (numpy, pytest, etc.) at the top of the test stub.
- Compute expected values using numpy / math arithmetic directly in the test body.
  Never call the function under test to obtain the expected value.
- Use pytest.approx() or numpy.allclose() for floating-point comparisons.
- Do NOT include the implementation — only tests.
- Every generated function must begin with a comment: # spec: <unit_id>

Respond with a single JSON object — no markdown fences, no extra keys:
{
  "role": "spec" | "definition" | "assumption" | "result" | "context" | "unknown",
  "confidence": <float 0-1>,
  "reasoning": "<one sentence>",
  "test_stub": "<pytest source with imports, or empty string>",
  "open_questions": ["<question if something is ambiguous>"]
}
"""

# Pass 2: implement the function so it passes the tests from pass 1.
_SYSTEM_CODE = """\
You are implementing a Python function to satisfy a set of pytest tests.
The tests encode the mathematical specification from a research paper.

Rules:
- The function name and signature must match exactly what the tests call.
- First line of every function: # spec: <unit_id>
- If the test stub contains a "# TODO: rename" comment, carry it into the implementation.
- Keep the implementation minimal and clean — no extra parameters, no classes.
- Import only what you use.
- Use the paper's own symbols as variable names where practical.

Respond with a single JSON object — no markdown fences, no extra keys:
{
  "code_stub": "<Python source>"
}
"""

_RE_FENCE = re.compile(r"```(?:json)?\s*")


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from the response, stripping markdown fences."""
    text = _RE_FENCE.sub("", text).strip().rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
    return json.loads(text[start:end])


def _user_prompt(unit: Unit, context: str, profile: Profile) -> str:
    """Build the user-turn prompt for pass 1 (classify + test)."""
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
        "Classify the TARGET unit and, if it is a spec, write the tests."
    )


def _code_prompt(unit: Unit, test_stub: str) -> str:
    """Build the user-turn prompt for pass 2 (implement from tests)."""
    return (
        f"Unit ID: {unit.id}\n\n"
        f"--- tests (the contract) ---\n{test_stub}\n--- end tests ---\n\n"
        f"--- LaTeX source ---\n{unit.raw}\n--- end source ---\n\n"
        "Implement the function so that all tests pass."
    )


async def _classify_and_test(
    unit: Unit,
    context: str,
    profile: Profile,
    completion,
) -> UnitResult:
    """Pass 1: classify the unit and generate tests (no implementation)."""
    response = await completion(
        model=profile.model,
        messages=[
            {"role": "system", "content": _SYSTEM_TEST},
            {"role": "user", "content": _user_prompt(unit, context, profile)},
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

    # code_stub is intentionally absent in pass 1 — default to empty.
    data.setdefault("code_stub", "")
    return UnitResult(**data)


async def _implement_from_tests(
    unit: Unit,
    test_stub: str,
    profile: Profile,
    completion,
) -> str:
    """Pass 2: generate code that satisfies the tests produced in pass 1."""
    response = await completion(
        model=profile.model,
        messages=[
            {"role": "system", "content": _SYSTEM_CODE},
            {"role": "user", "content": _code_prompt(unit, test_stub)},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    raw = response.choices[0].message.content
    try:
        data = _extract_json(raw)
        return data.get("code_stub", "")
    except (ValueError, KeyError):
        return ""


async def process_unit(
    unit: Unit,
    all_units: list[Unit],
    profile: Profile,
    *,
    glossary=None,
    _completion=None,
) -> UnitResult:
    """
    Classify *unit* and, if it is a spec, generate tested code via two async LLM calls.

    Pass 1 — classify + write tests (test-first):
      The LLM encodes the mathematical spec as pytest tests with independently
      computed expected values.  No implementation yet.

    Pass 2 — implement from tests (only for spec units):
      The LLM receives the tests as a contract and writes code to satisfy them.
      Because the two passes are independent, arithmetic errors in expected values
      surface as test failures rather than being silently baked into both sides.
    """
    completion = _completion if _completion is not None else litellm.acompletion
    context = build_context(unit, all_units, glossary)

    result = await _classify_and_test(unit, context, profile, completion)

    if result.role == Role.spec and result.test_stub:
        code_stub = await _implement_from_tests(unit, result.test_stub, profile, completion)
        result = result.model_copy(update={"code_stub": code_stub})

    return result
