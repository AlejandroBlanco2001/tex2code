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
_MAX_PROSE_CHUNKS = 4
_MIN_PARA_CHARS = 60  # skip very short paragraphs (headings, blank lines)

_STOP_WORDS = frozenset({
    "what", "the", "are", "for", "and", "that", "this", "from", "how",
    "which", "specific", "exact", "form", "forms", "function", "distribution",
    "should", "used", "does", "have", "can", "its", "with", "into", "where",
    "when", "their", "there", "define", "defined", "use", "any",
})

_RE_WORD = re.compile(r"\b\w{3,}\b")
_RE_LATEX_CMD = re.compile(r"\\[a-zA-Z]+")
# camelCase identifiers: fPhi, gPhi, qPhi, pT, pA — lowercase start, contains uppercase
_RE_CAMEL = re.compile(r"[a-z][a-zA-Z]*[A-Z][a-zA-Z]*")
# p(eps), q(zeta) — extract the variable name inside parens
_RE_PAREN_VAR = re.compile(r"\b[pqfgh]\((\w{2,})\)")

_REPHRASE_SYSTEM = """\
You are a search query optimizer for a mathematical research paper in LaTeX.
For each question, generate 3 short keyword queries (5 words max each) that would
help find the answer by searching the raw LaTeX source.
Focus on:
- LaTeX symbol names (e.g. "\\beps Gaussian prior")
- Equivalent terminology (e.g. "noise variable auxiliary distribution")
- LaTeX patterns that may appear literally (e.g. "mathcal N reparameterization")

Respond ONLY with a JSON object, no prose:
{"variants": [["q1_v1", "q1_v2", "q1_v3"], ["q2_v1", "q2_v2", "q2_v3"]]}
"""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_document",
            "description": (
                "Search the paper's structured units (equations, algorithms, definitions) "
                "for those whose LaTeX content matches the given keywords."
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
            "name": "search_prose",
            "description": (
                "Search the paper's unstructured prose text (paragraphs, captions, "
                "surrounding explanations) for passages matching the given keywords. "
                "Use this when the answer is likely stated in running text rather than "
                "inside an equation or algorithm block — e.g. dimension specifications, "
                "hyper-parameter values, or informal constraints."
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
Use the available tools to look for answers inside the paper:
- search_document — searches structured units (equations, algorithms, definitions)
- search_prose — searches unstructured running text (dimensions, hyper-parameters, informal constraints)
- get_unit — retrieves a specific unit's full LaTeX content by ID
Relevant passages have already been pre-loaded below each question — search further only if needed.
Prefer search_prose when the answer is likely stated in surrounding text (e.g. "the dimensionality … is d_model=512").

Mark a question answered=true if ANY of these hold:
- The paper gives an explicit answer (e.g. a formula, a distribution, a value).
- The paper gives a recommendation or example (e.g. "e.g. SGD or Adagrad") — good enough to implement.
- The paper gives a partial answer covering the main case (even if edge cases are left open).
- The mathematical definition is present, even if no Python code exists (code is derived from math).

Mark answered=false ONLY if the paper genuinely contains no relevant information — for example,
a convergence criterion that is left entirely to the practitioner with no guidance whatsoever.

Once you have finished, respond with ONLY a JSON object — no prose, no fences:
{
  "results": [
    {"answered": true, "evidence": "<one sentence citing the passage>"},
    {"answered": false, "evidence": ""}
  ]
}
One entry per question in the same order.
"""


def _extract_symbols(text: str) -> set[str]:
    """Extract LaTeX-style math identifiers from question text for exact search."""
    symbols: set[str] = set()
    for cmd in _RE_LATEX_CMD.findall(text):
        symbols.add(cmd)
    for name in _RE_CAMEL.findall(text):
        symbols.add(name)
        symbols.add(f"\\{name}")
    for var in _RE_PAREN_VAR.findall(text):
        # p(eps) → search for eps, \eps, \beps (common LaTeX bold prefix)
        symbols.update({var, f"\\{var}", f"\\b{var}"})
    return symbols


def _graph_neighbors(unit_id: str, deps: dict[str, set[str]]) -> set[str]:
    """Return direct predecessors and successors of *unit_id* in the dependency graph."""
    predecessors = deps.get(unit_id, set())
    successors = {uid for uid, d in deps.items() if unit_id in d}
    return predecessors | successors


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


def _gather_candidates(
    query: str,
    variants: list[str],
    all_units: list[Unit],
    exclude_id: str,
    *,
    symbols: set[str] | None = None,
    neighbor_ids: set[str] | None = None,
) -> list[Unit]:
    """
    Build a candidate pool combining three signals:
    1. Exact LaTeX symbol match (boosted score).
    2. Keyword overlap across the query and its rephrased variants.
    3. Graph neighbors (always included regardless of score).
    """
    unit_map = {u.id: u for u in all_units}
    scores: dict[str, int] = {}

    # 1. Symbol search — exact substring match on raw LaTeX, heavily boosted.
    if symbols:
        for unit in all_units:
            if unit.id == exclude_id:
                continue
            if any(sym in unit.raw for sym in symbols):
                scores[unit.id] = scores.get(unit.id, 0) + 5

    # 2. Keyword search over the original query and all variants.
    for q in [query] + variants:
        words = {w for w in _RE_WORD.findall(q.lower()) if w not in _STOP_WORDS}
        for unit in all_units:
            if unit.id == exclude_id:
                continue
            raw_lower = unit.raw.lower()
            hit = sum(1 for w in words if w in raw_lower)
            if hit:
                scores[unit.id] = scores.get(unit.id, 0) + hit

    ranked = sorted(
        [unit_map[uid] for uid in scores if uid in unit_map],
        key=lambda u: scores[u.id],
        reverse=True,
    )[:_MAX_CANDIDATES]

    # 3. Graph neighbors — append those not already ranked.
    if neighbor_ids:
        ranked_ids = {u.id for u in ranked}
        for uid in neighbor_ids:
            if uid != exclude_id and uid not in ranked_ids and uid in unit_map:
                ranked.append(unit_map[uid])

    return ranked


def _format_units(units: list[Unit]) -> str:
    """Format units as labelled passages for the LLM."""
    if not units:
        return "No matching units found."
    return "\n---\n".join(f"[{u.id}]\n{u.raw[:_MAX_PASSAGE_CHARS]}" for u in units)


def _search_prose(query: str, doc_text: str, *, symbols: set[str] | None = None) -> str:
    """
    Split *doc_text* into paragraphs and return the top-scoring ones for *query*.

    Scoring: symbol exact-match (+5) + keyword overlap (+1 per hit).
    Returns formatted text passages or a fallback message.
    """
    if not doc_text:
        return "No prose text available."

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", doc_text)]
    paragraphs = [p for p in paragraphs if len(p) >= _MIN_PARA_CHARS]

    words = {w for w in _RE_WORD.findall(query.lower()) if w not in _STOP_WORDS}
    scored: list[tuple[int, str]] = []
    for para in paragraphs:
        score = 0
        if symbols:
            score += 5 * sum(1 for sym in symbols if sym in para)
        para_lower = para.lower()
        score += sum(1 for w in words if w in para_lower)
        if score:
            scored.append((score, para))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:_MAX_PROSE_CHUNKS]
    if not top:
        return "No matching prose passages found."
    return "\n---\n".join(f"[prose]\n{p[:_MAX_PASSAGE_CHARS]}" for _, p in top)


async def _rephrase_questions(
    questions: list[str],
    profile: Profile,
    *,
    _completion=None,
) -> list[list[str]]:
    """
    Generate 3 search-optimised keyword variants per question in one LLM call.

    Returns a list parallel to *questions*; each element is a list of variant
    query strings.  Falls back to empty lists on any error so the caller
    degrades gracefully.
    """
    completion = _completion if _completion is not None else litellm.acompletion
    q_list = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    response = await completion(
        model=profile.model,
        messages=[
            {"role": "system", "content": _REPHRASE_SYSTEM},
            {"role": "user", "content": q_list},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    try:
        data = json.loads(response.choices[0].message.content)
        variants = data.get("variants", [])
        while len(variants) < len(questions):
            variants.append([])
        return variants[: len(questions)]
    except (json.JSONDecodeError, AttributeError):
        return [[] for _ in questions]


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
    deps: dict[str, set[str]] | None = None,
    doc_text: str = "",
    _completion=None,
) -> RevisionResult:
    """
    Agent-based revisor: the LLM searches the document to answer each question.

    Three search signals are combined before the agent loop starts:
    1. Question rephrasing — 3 keyword variants per question via a cheap LLM call.
    2. Symbol extraction — exact LaTeX command search (\\beps, \\pA, fPhi …).
    3. Graph traversal — dep-graph neighbours of the target unit are always included.

    Pre-searched passages are injected into the initial prompt so the agent
    starts with good context.  Tool calls (search_document, get_unit) are
    available for follow-up.
    """
    if not questions:
        return RevisionResult()

    completion = _completion if _completion is not None else litellm.acompletion
    unit_index = {u.id: u for u in all_units}

    # --- Pre-computation ---
    all_symbols = set().union(*(_extract_symbols(q) for q in questions))
    neighbor_ids = _graph_neighbors(unit.id, deps) if deps else set()
    variants_per_q = await _rephrase_questions(questions, profile, _completion=_completion)

    # Flatten all variants for shared search (used in tool calls too).
    all_variants = [v for vs in variants_per_q for v in vs]

    def _run_search_document(query: str) -> str:
        candidates = _gather_candidates(
            query,
            all_variants,
            all_units,
            unit.id,
            symbols=all_symbols,
            neighbor_ids=neighbor_ids,
        )
        return _format_units(candidates)

    def _run_search_prose(query: str) -> str:
        q_symbols = _extract_symbols(query) | all_symbols
        return _search_prose(query, doc_text, symbols=q_symbols)

    def _run_get_unit(unit_id: str) -> str:
        u = unit_index.get(unit_id)
        if u is None:
            return f"Unit '{unit_id}' not found. Try search_document to discover unit IDs."
        return f"[{u.id}]\n{u.raw}"

    # Build initial prompt with pre-loaded passages per question.
    parts: list[str] = []
    for q, variants in zip(questions, variants_per_q):
        q_symbols = _extract_symbols(q)
        candidates = _gather_candidates(
            q, variants, all_units, unit.id,
            symbols=q_symbols,
            neighbor_ids=neighbor_ids,
        )
        passages = _format_units(candidates)
        parts.append(f"Question: {q}\nPre-loaded passages:\n{passages}")

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Unit under review: '{unit.id}'\n\n"
                + "\n\n".join(parts)
                + "\n\nSearch further if needed, then give your verdict."
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

        for tc in tool_calls:
            args = json.loads(tc.function.arguments)
            if tc.function.name == "search_document":
                content = _run_search_document(args.get("query", ""))
            elif tc.function.name == "search_prose":
                content = _run_search_prose(args.get("query", ""))
            elif tc.function.name == "get_unit":
                content = _run_get_unit(args.get("unit_id", ""))
            else:
                content = f"Unknown tool: {tc.function.name}"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
    else:
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
