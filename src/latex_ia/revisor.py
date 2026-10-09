"""Revisor — agent that searches the document to answer open questions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import litellm

from latex_ia.models import Profile, Unit

_MAX_TOOL_ROUNDS = 4
_MAX_PASSAGE_CHARS = 800
_MAX_CANDIDATES = 6

_STOP_WORDS = frozenset({
    "what", "the", "are", "for", "and", "that", "this", "from", "how",
    "which", "specific", "exact", "form", "forms", "function", "distribution",
    "should", "used", "does", "have", "can", "its", "with", "into", "where",
    "when", "their", "there", "define", "defined", "use", "any",
})

_RE_WORD = re.compile(r"\b\w{3,}\b")

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_document",
            "description": (
                "Search the paper for units whose text contains the given keywords. "
                "Use this to find definitions, equations, or passages relevant to a question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords or symbol names to search for",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_unit",
            "description": "Retrieve the full LaTeX content of a specific unit by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "unit_id": {
                        "type": "string",
                        "description": "The unit ID to retrieve (e.g. 'def:encoder', 'eq:loss')",
                    }
                },
                "required": ["unit_id"],
            },
        },
    },
]

_SYSTEM = """\
You are reviewing open questions raised during analysis of a research paper section.
Use the search_document and get_unit tools to look for answers inside the paper.

Once you have finished searching, respond with ONLY a JSON object — no prose, no fences:
{
  "results": [
    {"answered": true, "evidence": "<one sentence citing the passage>"},
    {"answered": false, "evidence": ""}
  ]
}
One entry per question in the same order.
"""


def _search_units(query: str, all_units: list[Unit], exclude_id: str) -> list[Unit]:
    """Return the top-ranked units by keyword overlap with *query*."""
    words = {w for w in _RE_WORD.findall(query.lower()) if w not in _STOP_WORDS}
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


def _format_units(units: list[Unit]) -> str:
    """Format a list of units as labelled passages."""
    if not units:
        return "No matching units found."
    return "\n---\n".join(f"[{u.id}]\n{u.raw[:_MAX_PASSAGE_CHARS]}" for u in units)


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
    Agent-based revisor: the LLM searches the document to answer each question.

    Runs an agentic tool-call loop (up to _MAX_TOOL_ROUNDS) where the LLM
    can call search_document and get_unit.  Returns which questions are
    answered by the paper and which are genuinely missing.
    """
    if not questions:
        return RevisionResult()

    completion = _completion if _completion is not None else litellm.acompletion
    unit_index = {u.id: u for u in all_units}

    def _run_search_document(query: str) -> str:
        return _format_units(_search_units(query, all_units, unit.id))

    def _run_get_unit(unit_id: str) -> str:
        u = unit_index.get(unit_id)
        if u is None:
            return f"Unit '{unit_id}' not found. Try search_document to discover unit IDs."
        return f"[{u.id}]\n{u.raw}"

    q_list = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Questions about unit '{unit.id}':\n{q_list}\n\n"
                "Search the document to find answers, then give your verdict."
            ),
        },
    ]

    raw = ""
    for _ in range(_MAX_TOOL_ROUNDS):
        response = await completion(
            model=profile.model,
            messages=messages,
            tools=_TOOLS,
            temperature=0.0,
        )
        msg = response.choices[0].message
        tool_calls = msg.tool_calls or []

        if not tool_calls:
            raw = msg.content or ""
            break

        # Append assistant turn with tool calls.
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        # Execute tools and append results.
        for tc in tool_calls:
            args = json.loads(tc.function.arguments)
            if tc.function.name == "search_document":
                content = _run_search_document(args.get("query", ""))
            elif tc.function.name == "get_unit":
                content = _run_get_unit(args.get("unit_id", ""))
            else:
                content = f"Unknown tool: {tc.function.name}"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
    else:
        # Max rounds reached — ask for final verdict with forced JSON.
        messages.append({
            "role": "user",
            "content": "Provide your final verdict as the JSON object described above.",
        })
        response = await completion(
            model=profile.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        raw = response.choices[0].message.content or ""

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
    unresolved.extend(questions[len(results):])

    return RevisionResult(resolved=resolved, unresolved=unresolved)
