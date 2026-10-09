"""Revisor — checks open questions against the full document before surfacing them."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import litellm

from latex_ia.models import Profile, Unit

_STOP_WORDS = frozenset({
    "what", "the", "are", "for", "and", "that", "this", "from", "how",
    "which", "specific", "exact", "form", "forms", "function", "distribution",
    "should", "used", "does", "have", "can", "its", "with", "into", "where",
    "when", "their", "there", "define", "defined", "use", "used", "any",
})

_RE_WORD = re.compile(r"\b\w{3,}\b")

_MAX_CANDIDATES = 5
_MAX_PASSAGE_CHARS = 600

_SYSTEM = """\
You are reviewing open questions raised during analysis of a research paper section.
For each question, you are given the most relevant passages from elsewhere in the paper.
Decide whether the passage(s) answer the question.

Respond ONLY with a JSON object with a "results" array — one entry per question in the
same order, no extra keys:
{
  "results": [
    {"answered": true, "evidence": "<one sentence quoting or citing the passage>"},
    {"answered": false, "evidence": ""}
  ]
}
"""


def _search_units(question: str, all_units: list[Unit], exclude_id: str) -> list[Unit]:
    """Return up to _MAX_CANDIDATES units most relevant to the question by keyword overlap."""
    words = {w for w in _RE_WORD.findall(question.lower()) if w not in _STOP_WORDS}
    if not words:
        return []
    scored: list[tuple[int, Unit]] = []
    for unit in all_units:
        if unit.id == exclude_id:
            continue
        raw_lower = unit.raw.lower()
        score = sum(1 for w in words if w in raw_lower)
        if score:
            scored.append((score, unit))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [u for _, u in scored[:_MAX_CANDIDATES]]


@dataclass
class RevisionResult:
    """Outcome of the revisor pass for a single unit's open questions."""

    resolved: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


async def resolve_questions(
    unit: Unit,
    questions: list[str],
    all_units: list[Unit],
    profile: Profile,
    *,
    _completion=None,
) -> RevisionResult:
    """
    Check each open question against the full document.

    Searches the parsed document for relevant passages per question, then asks
    the LLM whether those passages answer each question.  Returns resolved
    (answerable from the paper) and unresolved (genuinely missing) questions.
    Only unresolved questions should be written to questions.md.
    """
    if not questions:
        return RevisionResult()

    completion = _completion if _completion is not None else litellm.acompletion

    parts: list[str] = []
    for i, q in enumerate(questions, 1):
        candidates = _search_units(q, all_units, unit.id)
        if candidates:
            passages = "\n---\n".join(
                f"[{u.id}]\n{u.raw[:_MAX_PASSAGE_CHARS]}" for u in candidates
            )
        else:
            passages = "(no relevant passages found in the document)"
        parts.append(f"Question {i}: {q}\nPassages:\n{passages}")

    response = await completion(
        model=profile.model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )

    raw = response.choices[0].message.content
    try:
        data = json.loads(raw)
        results = data.get("results", [])
    except (json.JSONDecodeError, AttributeError):
        return RevisionResult(unresolved=list(questions))

    resolved: list[str] = []
    unresolved: list[str] = []
    for q, entry in zip(questions, results):
        if isinstance(entry, dict) and entry.get("answered"):
            resolved.append(q)
        else:
            unresolved.append(q)

    # Questions beyond the parsed results are conservatively kept as unresolved.
    unresolved.extend(questions[len(results):])

    return RevisionResult(resolved=resolved, unresolved=unresolved)
